# Phase 5 LangGraph Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the sequential Pipeline loop with quota-safe LangGraph orchestration, parallelize Video and Voice, persist each generated asset for resume, and reload provider configuration on `/resume` without changing public API schemas.

**Architecture:** `Pipeline.run(...)` remains the public boundary and streams a compiled LangGraph, persisting merged `WorkflowState` after safe super-steps. Existing agents run through isolated adapters; Research routes conditionally, Video and Voice fan out in parallel, and their typed output JSON files become incremental manifests. A shared production-agent factory rebuilds provider clients from fresh `Settings()` during resume.

**Tech Stack:** Python 3.12, LangGraph 1.2.x, Pydantic v2, FastAPI, pytest, `threading.Barrier`, existing local JSON storage, existing Alibaba service wrappers.

---

## Implementation constraints

- Use TDD for every runtime behavior: test, observe expected failure, implement minimum code, rerun.
- Never invoke Alibaba, Wan, or CosyVoice during automated tests.
- Keep `/generate` synchronous and all API response schemas unchanged.
- Keep `longqiang_v3` and existing `.env` values untouched.
- Do not add a LangGraph checkpointer, background worker, approval endpoint, retry loop, orchestration feature flag, or legacy partial-file importer.
- Preserve `Pipeline(storage).run(job_id, agents, context)` for existing callers and partial-agent tests.
- Commit after every task using only named files.

## File map

- `requirements.txt`: pin supported LangGraph minor line.
- `agents/video.py`: incremental `VideoOutput` manifest and completed-clip reuse.
- `agents/voice.py`: incremental `VoiceOutput` manifest and completed-track reuse.
- `workflow/graph.py`: graph state, reducers, node adapters, conditional Research routing, parallel fan-out, join errors, graph compiler.
- `workflow/pipeline.py`: graph streaming, safe persistence, terminal status/error translation.
- `backend/factory.py`: construct all production services and seven agents from current settings.
- `backend/main.py`: use shared factory and provide a fresh-agent callback to API routes.
- `backend/api/routes.py`: rebuild agents when resume is called.
- `tests/test_workflow/test_graph.py` owns graph behavior; other tests stay beside their runtime units.

## Task 1: Add LangGraph dependency

**Files:**

- Modify: `requirements.txt`

- [ ] **Step 1: Add supported dependency range**

Add under Core:

```text
# Stateful workflow orchestration; minor line pinned for graph API stability.
langgraph>=1.2,<1.3
```

- [ ] **Step 2: Install repository requirements**

Run:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Expected: exit code 0 and a LangGraph 1.2.x package installed.

- [ ] **Step 3: Verify import and version line**

Run:

```powershell
.\venv\Scripts\python.exe -c "from importlib.metadata import version; from langgraph.graph import StateGraph; print(version('langgraph'))"
```

Expected: prints `1.2.x` and exits 0.

- [ ] **Step 4: Commit dependency**

```powershell
git add requirements.txt
git commit -m "build: add LangGraph orchestration dependency"
```

## Task 2: Persist and reuse Video assets incrementally

**Files:**

- Modify: `agents/video.py`
- Modify: `tests/test_agents/test_video.py`

- [ ] **Step 1: Make the existing mock service create valid files**

Replace `_mock_video_service` with:

```python
def _mock_video_service() -> MagicMock:
    mock = MagicMock(spec=VideoGenService)

    def generate(prompt: str, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"video")
        return str(path)

    mock.generate.side_effect = generate
    return mock
```

Import `Path` at module top and remove the local `PurePath` import inside a test.
For `test_run_returns_workflow_state`, `test_run_generates_clip_for_each_shot`,
and `test_run_persists_artifacts_to_storage`, add `tmp_path, monkeypatch` fixtures
and call `monkeypatch.chdir(tmp_path)` before `agent.run(...)`. In the storage
mock test, add:

```python
mock_storage.load.return_value = None
```

This prevents successful test media from being written into the repository and
makes the mocked storage represent an empty manifest.

- [ ] **Step 2: Write failing partial-manifest resume test**

Extend the context helper to accept two shots, or construct this Storyboard directly. Add:

```python
def test_run_persists_each_clip_and_resume_generates_only_missing(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    storage = LocalStorage("outputs")
    context = _make_context_with_storyboard(shot_count=2)
    first_service = _mock_video_service()

    def fail_second(prompt: str, output_path: str) -> str:
        if output_path.endswith("shot_002.mp4"):
            raise RuntimeError("quota exhausted")
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"first")
        return str(path)

    first_service.generate.side_effect = fail_second

    with pytest.raises(RuntimeError, match="quota exhausted"):
        VideoAgent(first_service, storage=storage).run(context)

    partial = VideoOutput.model_validate(
        storage.load("test-job", "video", "video_output.json")
    )
    assert [clip.shot_number for clip in partial.clips] == [1]

    resumed_service = _mock_video_service()
    result = VideoAgent(resumed_service, storage=storage).run(context)

    resumed_service.generate.assert_called_once()
    assert resumed_service.generate.call_args.args[1].endswith("shot_002.mp4")
    output = VideoOutput.model_validate(
        result.agent_results[AgentName.VIDEO].output_data
    )
    assert [clip.shot_number for clip in output.clips] == [1, 2]
```

Update `_make_context_with_storyboard(shot_count: int = 1)` to construct:

```python
storyboard = Storyboard(
    shots=[
        Shot(
            shot_number=number,
            scene_number=1,
            visual_prompt=f"Shot {number}",
            camera="wide",
            motion="static",
            duration=5.0,
        )
        for number in range(1, shot_count + 1)
    ]
)
```

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agents/test_video.py -k "persists_each_clip" -q
```

Expected: FAIL because Video Agent saves its manifest only after every clip succeeds.

- [ ] **Step 3: Implement manifest loading and safe reuse**

Add these helpers to `VideoAgent`:

```python
@staticmethod
def _is_reusable(clip: VideoClip) -> bool:
    path = Path(clip.file_path)
    return path.is_file() and path.stat().st_size > 0

def _load_manifest(self, job_id: str) -> dict[int, VideoClip]:
    if self.storage is None:
        return {}
    data = self.storage.load(
        job_id,
        self.name.value,
        "video_output.json",
    )
    if data is None:
        return {}
    output = VideoOutput.model_validate(data)
    return {clip.shot_number: clip for clip in output.clips}

def _save_manifest(self, job_id: str, clips: list[VideoClip]) -> None:
    if self.storage is None:
        return
    output = VideoOutput(clips=clips)
    self.storage.save(
        job_id,
        self.name.value,
        "video_output.json",
        output.model_dump(mode="json"),
    )
```

In `run`, load `completed = self._load_manifest(context.job_id)`. For every Storyboard shot:

```python
existing = completed.get(shot.shot_number)
if existing is not None and self._is_reusable(existing):
    clip = existing
else:
    output_path = self._clip_path(context.job_id, shot.shot_number)
    try:
        generated_path = self.video_service.generate(
            shot.visual_prompt,
            output_path,
        )
    except Exception as exc:
        if not self.fallback_enabled:
            raise RuntimeError(
                f"Video generation failed: {exc}. "
                "Set FALLBACK_STUBS=true to generate placeholder media, "
                "or configure VIDEO_API_KEY in .env."
            ) from exc
        raise NotImplementedError(
            "Fallback stub mode not implemented for VideoAgent"
        ) from exc
    clip = VideoClip(
        shot_number=shot.shot_number,
        file_path=generated_path,
        duration=shot.duration,
    )
    if not self._is_reusable(clip):
        raise RuntimeError(
            f"Video generation returned a missing or empty file: {generated_path}"
        )
    completed[shot.shot_number] = clip
    ordered_partial = [
        completed[item.shot_number]
        for item in storyboard.shots
        if item.shot_number in completed
        and self._is_reusable(completed[item.shot_number])
    ]
    self._save_manifest(context.job_id, ordered_partial)
clips.append(clip)
```

Keep final `VideoOutput`, artifacts, and `AgentResult` behavior. Replace the old single final storage block with `_save_manifest(context.job_id, clips)`.

- [ ] **Step 4: Test empty and missing saved files**

Add a parameterized test that first saves a manifest, then deletes or empties `shot_001.mp4`, reruns without a completed Video `AgentResult`, and asserts one provider call regenerates it:

```python
@pytest.mark.parametrize("damage", ["missing", "empty"])
def test_run_regenerates_invalid_manifest_file(tmp_path, monkeypatch, damage):
    monkeypatch.chdir(tmp_path)
    storage = LocalStorage("outputs")
    context = _make_context_with_storyboard()
    VideoAgent(_mock_video_service(), storage=storage).run(context)
    path = Path("outputs/test-job/video/clips/shot_001.mp4")
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(b"")
    del context.agent_results[AgentName.VIDEO]
    service = _mock_video_service()

    VideoAgent(service, storage=storage).run(context)

    service.generate.assert_called_once()
    assert path.stat().st_size > 0
```

- [ ] **Step 5: Run Video tests**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agents/test_video.py -q
```

Expected: all Video tests pass.

- [ ] **Step 6: Commit Video manifest support**

```powershell
git add agents/video.py tests/test_agents/test_video.py
git commit -m "feat(video): resume from completed clips"
```

## Task 3: Persist and reuse Voice assets incrementally

**Files:**

- Modify: `agents/voice.py`
- Modify: `tests/test_agents/test_voice.py`

- [ ] **Step 1: Make the mock TTS service create valid files**

Replace `_mock_tts_service` with:

```python
def _mock_tts_service() -> MagicMock:
    mock = MagicMock(spec=TTSService)

    def synthesize(text: str, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        return str(path)

    mock.synthesize.side_effect = synthesize
    return mock
```

For `test_run_returns_workflow_state`, `test_run_generates_track_for_each_scene`,
and `test_run_persists_artifacts_to_storage`, add `tmp_path, monkeypatch` fixtures
and call `monkeypatch.chdir(tmp_path)` before `agent.run(...)`. In the storage
mock test, set:

```python
mock_storage.load.return_value = None
```

- [ ] **Step 2: Write failing per-track resume test**

Update `_make_context_with_script(scene_count: int = 1)` to build scenes with:

```python
scenes=[
    Scene(
        scene_number=number,
        narration=f"Narration {number}",
        duration_hint=5.0,
        visual_direction=f"Visual {number}",
    )
    for number in range(1, scene_count + 1)
]
```

Add this failing test:

```python
def test_run_persists_each_track_and_resume_generates_only_missing(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    storage = LocalStorage("outputs")
    context = _make_context_with_script(scene_count=2)
    first_service = _mock_tts_service()

    def fail_second(text: str, output_path: str) -> str:
        if output_path.endswith("scene_002.mp3"):
            raise RuntimeError("voice quota exhausted")
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"first")
        return str(path)

    first_service.synthesize.side_effect = fail_second

    with pytest.raises(RuntimeError, match="voice quota exhausted"):
        VoiceAgent(first_service, storage=storage).run(context)

    partial = VoiceOutput.model_validate(
        storage.load("test-job", "voice", "voice_output.json")
    )
    assert [track.scene_number for track in partial.tracks] == [1]

    resumed_service = _mock_tts_service()
    result = VoiceAgent(resumed_service, storage=storage).run(context)

    resumed_service.synthesize.assert_called_once()
    assert resumed_service.synthesize.call_args.args[1].endswith(
        "scene_002.mp3"
    )
    output = VoiceOutput.model_validate(
        result.agent_results[AgentName.VOICE].output_data
    )
    assert [track.scene_number for track in output.tracks] == [1, 2]
```

Run and expect failure because Voice saves only after the whole loop:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agents/test_voice.py -k "persists_each_track" -q
```

- [ ] **Step 3: Implement Voice manifest helpers**

Add these typed Voice helpers:

```python
@staticmethod
def _is_reusable(track: AudioTrack) -> bool:
    path = Path(track.file_path)
    return path.is_file() and path.stat().st_size > 0

def _load_manifest(self, job_id: str) -> dict[int, AudioTrack]:
    if self.storage is None:
        return {}
    data = self.storage.load(
        job_id,
        self.name.value,
        "voice_output.json",
    )
    if data is None:
        return {}
    output = VoiceOutput.model_validate(data)
    return {track.scene_number: track for track in output.tracks}

def _save_manifest(self, job_id: str, tracks: list[AudioTrack]) -> None:
    if self.storage is None:
        return
    output = VoiceOutput(tracks=tracks)
    self.storage.save(
        job_id,
        self.name.value,
        "voice_output.json",
        output.model_dump(mode="json"),
    )
```

At the start of `run`, set `completed = self._load_manifest(context.job_id)`. Replace the track-generation loop body with:

```python
existing = completed.get(scene.scene_number)
if existing is not None and self._is_reusable(existing):
    track = existing
else:
    output_path = self._track_path(context.job_id, scene.scene_number)
    try:
        generated_path = self.tts_service.synthesize(
            scene.narration,
            output_path,
        )
    except Exception as exc:
        if not self.fallback_enabled:
            raise RuntimeError(
                f"Voice synthesis failed: {exc}. "
                "Set FALLBACK_STUBS=true to generate placeholder media, "
                "or configure VOICE_API_KEY in .env."
            ) from exc
        raise NotImplementedError(
            "Fallback stub mode not implemented for VoiceAgent"
        ) from exc
    track = AudioTrack(
        scene_number=scene.scene_number,
        file_path=generated_path,
        duration=scene.duration_hint,
    )
    if not self._is_reusable(track):
        raise RuntimeError(
            "Voice synthesis returned a missing or empty file: "
            f"{generated_path}"
        )
    completed[scene.scene_number] = track
    ordered_partial = [
        completed[item.scene_number]
        for item in script.scenes
        if item.scene_number in completed
        and self._is_reusable(completed[item.scene_number])
    ]
    self._save_manifest(context.job_id, ordered_partial)
tracks.append(track)
```

Save the complete manifest again before writing final `AgentResult`.

Use this exact invalid-media error:

```python
raise RuntimeError(
    f"Voice synthesis returned a missing or empty file: {generated_path}"
)
```

- [ ] **Step 4: Add missing/empty track regeneration test**

Add:

```python
@pytest.mark.parametrize("damage", ["missing", "empty"])
def test_run_regenerates_invalid_manifest_file(tmp_path, monkeypatch, damage):
    monkeypatch.chdir(tmp_path)
    storage = LocalStorage("outputs")
    context = _make_context_with_script()
    VoiceAgent(_mock_tts_service(), storage=storage).run(context)
    path = Path("outputs/test-job/voice/audio/scene_001.mp3")
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(b"")
    del context.agent_results[AgentName.VOICE]
    service = _mock_tts_service()

    VoiceAgent(service, storage=storage).run(context)

    service.synthesize.assert_called_once()
    assert path.stat().st_size > 0
```

- [ ] **Step 5: Run Voice tests**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agents/test_voice.py -q
```

Expected: all Voice tests pass.

- [ ] **Step 6: Commit Voice manifest support**

```powershell
git add agents/voice.py tests/test_agents/test_voice.py
git commit -m "feat(voice): resume from completed tracks"
```

## Task 4: Build graph state, adapters, and conditional Research routing

**Files:**

- Create: `tests/test_workflow/test_graph.py`
- Modify: `workflow/graph.py`

- [ ] **Step 1: Write failing conditional routing tests**

Create `tests/test_workflow/test_graph.py` with these imports and helpers:

```python
import threading
from unittest.mock import MagicMock

from agents.base import BaseAgent
from agents.research import ResearchAgent
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from models.enums import AgentName
from models.workflow_state import WorkflowState
from storage.local import LocalStorage
from tools.llm import LLMService
from workflow.graph import (
    ParallelAgentError,
    build_pipeline_graph,
    workflow_to_graph_state,
)


class RecordingAgent(BaseAgent):
    def __init__(self, name: AgentName, calls: list[AgentName]) -> None:
        self.name = name
        self.calls = calls
        super().__init__()

    def run(self, context: WorkflowState) -> WorkflowState:
        self.calls.append(self.name)
        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data={"ran": True},
        )
        return context


def _upstream_context(requires_research: bool) -> WorkflowState:
    context = WorkflowState(job_id="graph-job", prompt="test")
    brief = CreativeBrief(
        title="T",
        prompt="test",
        tone="clear",
        audience="general",
        duration_seconds=5,
        summary="S",
        requires_research=requires_research,
    )
    context.agent_results[AgentName.DIRECTOR] = AgentResult(
        agent_name=AgentName.DIRECTOR,
        success=True,
        output_data=brief.model_dump(mode="json"),
    )
    return context


def _full_recording_agents(storage, llm):
    calls: list[AgentName] = []
    agents = [
        RecordingAgent(AgentName.DIRECTOR, calls),
        ResearchAgent(llm, storage),
        RecordingAgent(AgentName.SCRIPT, calls),
        RecordingAgent(AgentName.STORYBOARD, calls),
        RecordingAgent(AgentName.VIDEO, calls),
        RecordingAgent(AgentName.VOICE, calls),
        RecordingAgent(AgentName.EDITOR, calls),
    ]
    return agents, calls
```

Add the tests:

```python
def test_creative_brief_routes_through_skip_research(tmp_path):
    storage = LocalStorage(str(tmp_path))
    llm = MagicMock(spec=LLMService)
    context = _upstream_context(requires_research=False)
    agents, calls = _full_recording_agents(storage, llm)

    states = list(
        build_pipeline_graph(agents).stream(
            workflow_to_graph_state(context),
            stream_mode="values",
        )
    )

    final = states[-1]
    assert AgentName.RESEARCH in final["agent_results"]
    llm.generate.assert_not_called()
    assert AgentName.DIRECTOR not in calls
    assert AgentName.SCRIPT in calls


def test_factual_brief_calls_research_llm(tmp_path):
    storage = LocalStorage(str(tmp_path))
    llm = MagicMock(spec=LLMService)
    llm.generate.return_value = (
        '{"brief_summary":"facts","notes":[],"overall_confidence":0.0}'
    )
    context = _upstream_context(requires_research=True)
    agents, _ = _full_recording_agents(storage, llm)

    list(
        build_pipeline_graph(agents).stream(
            workflow_to_graph_state(context),
            stream_mode="values",
        )
    )

    llm.generate.assert_called_once()
```

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_workflow/test_graph.py -q
```

Expected: collection FAIL because graph functions do not exist.

- [ ] **Step 2: Implement graph types and conversion helpers**

In `workflow/graph.py`, define:

```python
from __future__ import annotations

import operator
from datetime import datetime, timezone
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.base import BaseAgent
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from models.enums import AgentName, JobStatus
from models.workflow_state import WorkflowState


class BranchFailure(TypedDict):
    agent_name: AgentName
    error: str


def merge_agent_results(
    current: dict[AgentName, AgentResult],
    update: dict[AgentName, AgentResult],
) -> dict[AgentName, AgentResult]:
    return {**current, **update}


class PipelineGraphState(TypedDict):
    job_id: str
    prompt: str
    created_at: datetime
    agent_results: Annotated[
        dict[AgentName, AgentResult],
        merge_agent_results,
    ]
    branch_failures: Annotated[list[BranchFailure], operator.add]


class AgentNodeError(RuntimeError):
    def __init__(self, agent_name: AgentName, message: str) -> None:
        self.agent_name = agent_name
        super().__init__(message)


class ParallelAgentError(RuntimeError):
    def __init__(self, failures: list[BranchFailure]) -> None:
        ordered = sorted(
            failures,
            key=lambda item: (
                0 if item["agent_name"] == AgentName.VIDEO else 1,
                item["agent_name"].value,
            ),
        )
        self.failures = ordered
        self.agent_name = ordered[0]["agent_name"]
        message = "; ".join(
            f"{item['agent_name'].value}: {item['error']}"
            for item in ordered
        )
        super().__init__(message)


def workflow_to_graph_state(context: WorkflowState) -> PipelineGraphState:
    return {
        "job_id": context.job_id,
        "prompt": context.prompt,
        "created_at": context.created_at,
        "agent_results": dict(context.agent_results),
        "branch_failures": [],
    }


def graph_state_to_workflow(
    state: PipelineGraphState,
    status: JobStatus = JobStatus.RUNNING,
) -> WorkflowState:
    return WorkflowState(
        job_id=state["job_id"],
        prompt=state["prompt"],
        status=status,
        current_agent=None,
        agent_results=dict(state.get("agent_results", {})),
        created_at=state["created_at"],
        updated_at=datetime.now(timezone.utc),
    )
```

- [ ] **Step 3: Implement isolated agent adapters**

```python
def make_agent_node(
    agent: BaseAgent,
    capture_failure: bool = False,
):
    def node(state: PipelineGraphState) -> dict:
        if agent.name in state.get("agent_results", {}):
            return {}
        context = graph_state_to_workflow(state)
        try:
            result = agent.run(context.model_copy(deep=True))
        except Exception as exc:
            if capture_failure:
                return {
                    "branch_failures": [
                        {
                            "agent_name": agent.name,
                            "error": str(exc),
                        }
                    ]
                }
            raise AgentNodeError(agent.name, str(exc)) from exc
        agent_result = result.agent_results.get(agent.name)
        if agent_result is None:
            raise AgentNodeError(
                agent.name,
                f"Agent {agent.name.value} returned no AgentResult",
            )
        return {"agent_results": {agent.name: agent_result}}

    return node
```

- [ ] **Step 4: Implement full and compatibility graph builders**

The full graph requires exactly the canonical seven names. Both Research branches use the same `ResearchAgent` adapter; the agent's existing creative path makes zero LLM calls.

```python
FULL_PIPELINE = [
    AgentName.DIRECTOR,
    AgentName.RESEARCH,
    AgentName.SCRIPT,
    AgentName.STORYBOARD,
    AgentName.VIDEO,
    AgentName.VOICE,
    AgentName.EDITOR,
]


def _index_agents(agents: list[BaseAgent]) -> dict[AgentName, BaseAgent]:
    indexed: dict[AgentName, BaseAgent] = {}
    for agent in agents:
        if agent.name in indexed:
            raise ValueError(f"Duplicate pipeline agent: {agent.name.value}")
        indexed[agent.name] = agent
    return indexed


def _route_research(state: PipelineGraphState) -> str:
    if AgentName.RESEARCH in state.get("agent_results", {}):
        return "research"
    result = state["agent_results"][AgentName.DIRECTOR]
    try:
        brief = CreativeBrief.model_validate(result.output_data)
    except Exception:
        return "research"
    return "research" if brief.requires_research else "skip_research"


def _asset_join(state: PipelineGraphState) -> dict:
    failures = state.get("branch_failures", [])
    if failures:
        raise ParallelAgentError(failures)
    missing = [
        name.value
        for name in (AgentName.VIDEO, AgentName.VOICE)
        if name not in state.get("agent_results", {})
    ]
    if missing:
        raise AgentNodeError(
            AgentName.VIDEO,
            f"Asset join missing successful results: {', '.join(missing)}",
        )
    return {}


def _build_full_graph(indexed: dict[AgentName, BaseAgent]):
    builder = StateGraph(PipelineGraphState)
    builder.add_node("director", make_agent_node(indexed[AgentName.DIRECTOR]))
    builder.add_node("research", make_agent_node(indexed[AgentName.RESEARCH]))
    builder.add_node(
        "skip_research",
        make_agent_node(indexed[AgentName.RESEARCH]),
    )
    builder.add_node("script", make_agent_node(indexed[AgentName.SCRIPT]))
    builder.add_node(
        "storyboard",
        make_agent_node(indexed[AgentName.STORYBOARD]),
    )
    builder.add_node(
        "video",
        make_agent_node(indexed[AgentName.VIDEO], capture_failure=True),
    )
    builder.add_node(
        "voice",
        make_agent_node(indexed[AgentName.VOICE], capture_failure=True),
    )
    builder.add_node("asset_join", _asset_join)
    builder.add_node("editor", make_agent_node(indexed[AgentName.EDITOR]))
    builder.add_edge(START, "director")
    builder.add_conditional_edges(
        "director",
        _route_research,
        {"research": "research", "skip_research": "skip_research"},
    )
    builder.add_edge("research", "script")
    builder.add_edge("skip_research", "script")
    builder.add_edge("script", "storyboard")
    builder.add_edge("storyboard", "video")
    builder.add_edge("storyboard", "voice")
    builder.add_edge(["video", "voice"], "asset_join")
    builder.add_edge("asset_join", "editor")
    builder.add_edge("editor", END)
    return builder.compile()


def _build_compatibility_graph(agents: list[BaseAgent]):
    builder = StateGraph(PipelineGraphState)
    if not agents:
        return None
    names: list[str] = []
    for index, agent in enumerate(agents):
        node_name = f"{index:03d}_{agent.name.value}"
        names.append(node_name)
        builder.add_node(node_name, make_agent_node(agent))
    builder.add_edge(START, names[0])
    for current, following in zip(names, names[1:]):
        builder.add_edge(current, following)
    builder.add_edge(names[-1], END)
    return builder.compile()


def build_pipeline_graph(agents: list[BaseAgent]):
    indexed = _index_agents(agents)
    if list(indexed) == FULL_PIPELINE and len(agents) == len(FULL_PIPELINE):
        return _build_full_graph(indexed)
    return _build_compatibility_graph(agents)
```

- [ ] **Step 5: Run conditional graph tests**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_workflow/test_graph.py -q
```

Expected: conditional routing tests pass.

- [ ] **Step 6: Commit graph foundation**

```powershell
git add workflow/graph.py tests/test_workflow/test_graph.py
git commit -m "feat(graph): add conditional LangGraph workflow"
```

## Task 5: Prove parallel isolation and deterministic branch failure

**Files:**

- Modify: `tests/test_workflow/test_graph.py`
- Modify: `workflow/graph.py`

- [ ] **Step 1: Write parallel overlap test**

Add imports and fixtures:

```python
import pytest

from models.research import ResearchNotes
from models.scene import Scene
from models.script import Script
from models.storyboard import Shot, Storyboard


class FailingAgent(BaseAgent):
    def __init__(self, name: AgentName, message: str) -> None:
        self.name = name
        self.message = message
        super().__init__()

    def run(self, context: WorkflowState) -> WorkflowState:
        raise RuntimeError(self.message)


def _context_through_storyboard() -> WorkflowState:
    context = _upstream_context(requires_research=False)
    values = {
        AgentName.RESEARCH: ResearchNotes(
            brief_summary="skipped",
            notes=[],
            overall_confidence=0,
        ),
        AgentName.SCRIPT: Script(
            title="T",
            scenes=[
                Scene(
                    scene_number=1,
                    narration="N",
                    duration_hint=5,
                    visual_direction="V",
                )
            ],
        ),
        AgentName.STORYBOARD: Storyboard(
            shots=[
                Shot(
                    shot_number=1,
                    scene_number=1,
                    visual_prompt="V",
                    camera="wide",
                    motion="static",
                    duration=5,
                )
            ]
        ),
    }
    for name, value in values.items():
        context.agent_results[name] = AgentResult(
            agent_name=name,
            success=True,
            output_data=value.model_dump(mode="json"),
        )
    return context


def _agents_with_assets(video, voice, editor):
    return [
        RecordingAgent(AgentName.DIRECTOR, []),
        RecordingAgent(AgentName.RESEARCH, []),
        RecordingAgent(AgentName.SCRIPT, []),
        RecordingAgent(AgentName.STORYBOARD, []),
        video,
        voice,
        editor,
    ]
```

Use a two-party barrier so sequential execution fails without relying on wall-clock timing:

```python
class BarrierAgent(BaseAgent):
    def __init__(self, name: AgentName, barrier: threading.Barrier) -> None:
        self.name = name
        self.barrier = barrier
        super().__init__()

    def run(self, context: WorkflowState) -> WorkflowState:
        self.barrier.wait(timeout=2)
        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data={"ran": True},
        )
        return context


def test_video_and_voice_execute_in_parallel():
    barrier = threading.Barrier(2)
    context = _context_through_storyboard()
    agents = _agents_with_assets(
        video=BarrierAgent(AgentName.VIDEO, barrier),
        voice=BarrierAgent(AgentName.VOICE, barrier),
        editor=RecordingAgent(AgentName.EDITOR, []),
    )

    final = list(
        build_pipeline_graph(agents).stream(
            workflow_to_graph_state(context),
            stream_mode="values",
        )
    )[-1]

    assert AgentName.VIDEO in final["agent_results"]
    assert AgentName.VOICE in final["agent_results"]
    assert AgentName.EDITOR in final["agent_results"]
```

Run and expect PASS if Task 4 fan-out is correct:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_workflow/test_graph.py -k "execute_in_parallel" -q
```

- [ ] **Step 2: Write one-branch failure preservation test**

```python
def test_voice_success_survives_video_failure():
    context = _context_through_storyboard()
    agents = _agents_with_assets(
        video=FailingAgent(AgentName.VIDEO, "video quota"),
        voice=RecordingAgent(AgentName.VOICE, []),
        editor=RecordingAgent(AgentName.EDITOR, []),
    )
    graph = build_pipeline_graph(agents)
    results = dict(context.agent_results)

    with pytest.raises(ParallelAgentError) as caught:
        for mode, chunk in graph.stream(
            workflow_to_graph_state(context),
            stream_mode=["updates", "values"],
        ):
            if mode == "values":
                results.update(chunk.get("agent_results", {}))
            else:
                for node_update in chunk.values():
                    if isinstance(node_update, dict):
                        results.update(
                            node_update.get("agent_results", {})
                        )

    assert caught.value.agent_name == AgentName.VIDEO
    assert AgentName.VOICE in results
    assert AgentName.EDITOR not in results
```

- [ ] **Step 3: Write dual-failure ordering test**

```python
def test_parallel_failures_choose_video_and_combine_errors():
    context = _context_through_storyboard()
    agents = _agents_with_assets(
        video=FailingAgent(AgentName.VIDEO, "video quota"),
        voice=FailingAgent(AgentName.VOICE, "voice quota"),
        editor=RecordingAgent(AgentName.EDITOR, []),
    )

    with pytest.raises(ParallelAgentError) as caught:
        list(
            build_pipeline_graph(agents).stream(
                workflow_to_graph_state(context),
                stream_mode="values",
            )
        )

    assert caught.value.agent_name == AgentName.VIDEO
    assert str(caught.value) == "video: video quota; voice: voice quota"
```

- [ ] **Step 4: Run graph test file**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_workflow/test_graph.py -q
```

Expected: all graph tests pass. The Pipeline integration in Task 6 consumes both `updates` and `values`, ensuring successful parallel writes are captured before a failing join.

- [ ] **Step 5: Commit parallel graph behavior**

```powershell
git add workflow/graph.py tests/test_workflow/test_graph.py
git commit -m "feat(graph): run asset agents in parallel"
```

## Task 6: Make Pipeline stream and persist graph state

**Files:**

- Modify: `workflow/pipeline.py`
- Modify: `workflow/resume.py`
- Modify: `tests/test_workflow/test_pipeline.py`
- Modify: `tests/test_workflow/test_resume.py`

- [ ] **Step 1: Add Pipeline graph regression tests**

Preserve existing test cases. Add these imports:

```python
from models.brief import CreativeBrief
from models.research import ResearchNotes
from models.scene import Scene
from models.script import Script
from models.storyboard import Shot, Storyboard
```

Add these local fixtures to `tests/test_workflow/test_pipeline.py`:

```python
class MessageFailAgent(StubAgent):
    def __init__(self, name: AgentName, message: str) -> None:
        super().__init__(name)
        self.message = message

    def run(self, context: WorkflowState) -> WorkflowState:
        raise RuntimeError(self.message)


def _context_through_storyboard(job_id: str) -> WorkflowState:
    context = WorkflowState(job_id=job_id, prompt="creative")
    values = {
        AgentName.DIRECTOR: CreativeBrief(
            title="T",
            prompt="creative",
            tone="clear",
            audience="general",
            duration_seconds=5,
            summary="S",
            requires_research=False,
        ),
        AgentName.RESEARCH: ResearchNotes(
            brief_summary="skipped",
            notes=[],
            overall_confidence=0,
        ),
        AgentName.SCRIPT: Script(
            title="T",
            scenes=[
                Scene(
                    scene_number=1,
                    narration="N",
                    duration_hint=5,
                    visual_direction="V",
                )
            ],
        ),
        AgentName.STORYBOARD: Storyboard(
            shots=[
                Shot(
                    shot_number=1,
                    scene_number=1,
                    visual_prompt="V",
                    camera="wide",
                    motion="static",
                    duration=5,
                )
            ]
        ),
    }
    for name, value in values.items():
        context.agent_results[name] = AgentResult(
            agent_name=name,
            success=True,
            output_data=value.model_dump(mode="json"),
        )
    return context


def _full_agents_with_assets(video, voice, editor) -> list[BaseAgent]:
    return [
        StubAgent(AgentName.DIRECTOR),
        StubAgent(AgentName.RESEARCH),
        StubAgent(AgentName.SCRIPT),
        StubAgent(AgentName.STORYBOARD),
        video,
        voice,
        editor,
    ]
```

Then add:

```python
def test_pipeline_persists_parallel_success_before_failure(tmp_path):
    storage = LocalStorage(str(tmp_path))
    context = _context_through_storyboard(job_id="parallel-fail")
    agents = _full_agents_with_assets(
        video=MessageFailAgent(AgentName.VIDEO, "quota"),
        voice=StubAgent(AgentName.VOICE),
        editor=StubAgent(AgentName.EDITOR),
    )

    result = Pipeline(storage).run("parallel-fail", agents, context)

    assert result.status == JobStatus.FAILED
    assert result.failed_agent == AgentName.VIDEO
    assert result.current_agent is None
    assert AgentName.VOICE in result.agent_results
    assert AgentName.EDITOR not in result.agent_results
    saved = WorkflowState.model_validate(
        storage.load("parallel-fail", "pipeline", "context.json")
    )
    assert AgentName.VOICE in saved.agent_results
```

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_workflow/test_pipeline.py -q
```

Expected: new test FAIL because current Pipeline runs Video then stops before Voice.

- [ ] **Step 2: Replace Pipeline loop with graph streaming**

Keep `_persist_context`. Add a stream-update helper to `Pipeline`:

```python
@staticmethod
def _apply_update(latest: dict, chunk: dict) -> dict:
    merged = dict(latest)
    results = dict(merged.get("agent_results", {}))
    failures = list(merged.get("branch_failures", []))
    for node_update in chunk.values():
        if not isinstance(node_update, dict):
            continue
        results.update(node_update.get("agent_results", {}))
        failures.extend(node_update.get("branch_failures", []))
    merged["agent_results"] = results
    merged["branch_failures"] = failures
    return merged
```

Implement `run`:

```python
from datetime import datetime, timezone

from workflow.graph import (
    AgentNodeError,
    ParallelAgentError,
    build_pipeline_graph,
    graph_state_to_workflow,
    workflow_to_graph_state,
)


def run(
    self,
    job_id: str,
    agents: list[BaseAgent],
    context: WorkflowState,
) -> WorkflowState:
    context.status = JobStatus.RUNNING
    context.current_agent = None
    context.failed_agent = None
    context.error = None
    context.updated_at = datetime.now(timezone.utc)
    self._persist_context(job_id, context)

    latest = workflow_to_graph_state(context)
    try:
        graph = build_pipeline_graph(agents)
        if graph is None:
            context.status = JobStatus.COMPLETED
            context.updated_at = datetime.now(timezone.utc)
            self._persist_context(job_id, context)
            return context
        for mode, chunk in graph.stream(
            latest,
            stream_mode=["updates", "values"],
        ):
            if mode == "values":
                latest = chunk
            else:
                latest = self._apply_update(latest, chunk)
            context = graph_state_to_workflow(latest)
            self._persist_context(job_id, context)
    except (AgentNodeError, ParallelAgentError) as exc:
        context = graph_state_to_workflow(latest, status=JobStatus.FAILED)
        context.failed_agent = exc.agent_name
        context.error = str(exc)
        context.updated_at = datetime.now(timezone.utc)
        self._persist_context(job_id, context)
        return context
    except Exception as exc:
        context = graph_state_to_workflow(latest, status=JobStatus.FAILED)
        context.error = f"Graph execution failed: {exc}"
        context.updated_at = datetime.now(timezone.utc)
        self._persist_context(job_id, context)
        return context

    context = graph_state_to_workflow(latest, status=JobStatus.COMPLETED)
    context.updated_at = datetime.now(timezone.utc)
    self._persist_context(job_id, context)
    return context
```

Keep `run` as a class method body, not a free function.

- [ ] **Step 3: Preserve partial-agent compatibility tests**

In `workflow/resume.py`, remove `remaining_agents` filtering. Completed nodes now
self-skip inside LangGraph, so resume must pass the complete configured graph:

```python
context.failed_agent = None
context.error = None
return Pipeline(storage).run(job_id, agents, context)
```

This allows a resume where both Video and Voice are incomplete to fan out again.
Existing call-order assertions remain valid because completed node adapters return
without calling their agents.

Run existing Pipeline and resume tests:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_workflow/test_pipeline.py tests/test_workflow/test_resume.py -q
```

Expected: all existing sequential partial-agent tests pass through `_build_compatibility_graph`; the new parallel persistence test passes.

- [ ] **Step 4: Commit Pipeline migration**

```powershell
git add workflow/pipeline.py workflow/resume.py tests/test_workflow/test_pipeline.py tests/test_workflow/test_resume.py
git commit -m "refactor: run Pipeline through LangGraph"
```

## Task 7: Extract production agent factory

**Files:**

- Create: `backend/factory.py`
- Create: `tests/test_backend/test_factory.py`

- [ ] **Step 1: Write failing factory test**

Create `tests/test_backend/test_factory.py` with:

```python
from backend.config import Settings
from backend.factory import build_production_agents
from models.enums import AgentName
from storage.local import LocalStorage
```

```python
def test_build_production_agents_uses_supplied_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("VIDEO_MODEL", "wan-test")
    monkeypatch.setenv("VOICE_MODEL", "cosy-test")
    monkeypatch.setenv("VOICE_VOICE", "longqiang_v3")
    settings = Settings()
    storage = LocalStorage(str(tmp_path))

    agents = build_production_agents(
        settings,
        storage,
        output_dir=tmp_path,
    )

    indexed = {agent.name: agent for agent in agents}
    assert indexed[AgentName.VIDEO].video_service.config.model == "wan-test"
    assert indexed[AgentName.VOICE].tts_service.config.model == "cosy-test"
    assert indexed[AgentName.VOICE].tts_service.config.voice == "longqiang_v3"
    assert len(agents) == 7
```

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_backend/test_factory.py -q
```

Expected: collection FAIL because `backend.factory` does not exist.

- [ ] **Step 2: Implement focused factory**

Create `backend/factory.py`:

```python
from pathlib import Path

from agents.base import BaseAgent
from agents.director import DirectorAgent
from agents.editor import EditorAgent
from agents.research import ResearchAgent
from agents.script import ScriptAgent
from agents.storyboard import StoryboardAgent
from agents.video import VideoAgent
from agents.voice import VoiceAgent
from backend.config import Settings
from storage.base import StorageBackend
from tools.ffmpeg import LocalFFmpegService
from tools.llm import AlibabaCloudLLMService
from tools.tts import DashScopeTTSService
from tools.video_gen import DashScopeVideoGenService


def build_production_agents(
    settings: Settings,
    storage: StorageBackend,
    output_dir: str | Path,
    fallback_enabled: bool = False,
) -> list[BaseAgent]:
    llm = AlibabaCloudLLMService(settings.llm)
    video = DashScopeVideoGenService(settings.video)
    voice = DashScopeTTSService(settings.voice)
    return [
        DirectorAgent(llm, storage),
        ResearchAgent(llm, storage),
        ScriptAgent(llm, storage),
        StoryboardAgent(llm, storage),
        VideoAgent(video, storage, fallback_enabled),
        VoiceAgent(voice, storage, fallback_enabled),
        EditorAgent(LocalFFmpegService(), storage, output_dir),
    ]
```

- [ ] **Step 3: Run factory test**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_backend/test_factory.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit factory extraction**

```powershell
git add backend/factory.py tests/test_backend/test_factory.py
git commit -m "refactor: centralize production agent construction"
```

## Task 8: Reload `.env` and agents on resume

**Files:**

- Modify: `backend/api/routes.py`
- Modify: `backend/main.py`
- Modify: `tests/test_api/test_routes.py`
- Modify: `tests/test_backend/test_main.py`

- [ ] **Step 1: Write failing route factory test**

Add:

```python
def test_resume_builds_fresh_agents_from_factory():
    storage = InMemoryStorage()
    job_store: dict[str, JobRecord] = {}
    call_order: list[AgentName] = []
    fresh = [CompletingEditor(call_order)]
    factory = MagicMock(return_value=fresh)
    app = create_app(
        storage=storage,
        job_store=job_store,
        agents=[FailingIfCalledEditor()],
        agent_factory=factory,
    )
    client = TestClient(app)
    job_id = _failed_editor_job(storage, job_store)

    response = client.post(f"/resume/{job_id}")

    assert response.status_code == 202
    factory.assert_called_once_with()
    assert call_order == [AgentName.EDITOR]
```

Add this stale-agent guard:

```python
class FailingIfCalledEditor(BaseAgent):
    name = AgentName.EDITOR

    def run(self, context: WorkflowState) -> WorkflowState:
        raise AssertionError("stale agents used")
```

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_api/test_routes.py -k "fresh_agents" -q
```

Expected: FAIL because `create_app` has no `agent_factory` parameter.

- [ ] **Step 2: Inject and use fresh-agent callback**

Add imports:

```python
from collections.abc import Callable
```

Change `create_app` signature:

```python
def create_app(
    storage: StorageBackend,
    job_store: dict[str, JobRecord],
    agents: list[BaseAgent] | None = None,
    agent_factory: Callable[[], list[BaseAgent]] | None = None,
) -> FastAPI:
```

In resume:

```python
resume_agents = agent_factory() if agent_factory is not None else agents
if not resume_agents:
    raise HTTPException(
        status_code=503,
        detail="Resume is unavailable: no agents configured",
    )
context = resume_job(job_id, resume_agents, storage)
```

Remove the old `if not agents` block.

- [ ] **Step 3: Wire production app to the shared factory**

In `backend/main.py`, remove direct service/agent imports and import:

```python
from backend.factory import build_production_agents
```

Replace `create_production_app` with:

```python
def create_production_app():
    initial_settings = Settings()
    storage = LocalStorage(initial_settings.storage.output_dir)
    job_store: dict[str, JobRecord] = {}
    fallback_enabled = (
        os.environ.get("FALLBACK_STUBS", "false").lower() == "true"
    )

    def agent_factory():
        return build_production_agents(
            Settings(),
            storage,
            output_dir=initial_settings.storage.output_dir,
            fallback_enabled=fallback_enabled,
        )

    agents = agent_factory()
    return create_app(
        storage=storage,
        job_store=job_store,
        agents=agents,
        agent_factory=agent_factory,
    )
```

Update `test_production_app_includes_editor_as_seventh_agent`:

```python
def capture_app(storage, job_store, agents, agent_factory):
    captured["agents"] = agents
    captured["agent_factory"] = agent_factory
    return object()

# Existing seven-name assertion remains.
assert callable(captured["agent_factory"])
```

- [ ] **Step 4: Prove fresh Settings reread `.env`**

In `tests/test_backend/test_factory.py`, add:

```python
def test_new_settings_instance_reads_changed_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VIDEO_MODEL", raising=False)
    monkeypatch.delenv("VOICE_MODEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "VIDEO_MODEL=wan-first\nVOICE_MODEL=cosy-first\n",
        encoding="utf-8",
    )
    storage = LocalStorage(str(tmp_path / "outputs"))
    first = build_production_agents(
        Settings(),
        storage,
        output_dir=tmp_path / "outputs",
    )
    env_file.write_text(
        "VIDEO_MODEL=wan-second\nVOICE_MODEL=cosy-second\n",
        encoding="utf-8",
    )
    second = build_production_agents(
        Settings(),
        storage,
        output_dir=tmp_path / "outputs",
    )
    first_by_name = {agent.name: agent for agent in first}
    second_by_name = {agent.name: agent for agent in second}

    assert first_by_name[AgentName.VIDEO].video_service.config.model == "wan-first"
    assert second_by_name[AgentName.VIDEO].video_service.config.model == "wan-second"
    assert first_by_name[AgentName.VOICE].tts_service.config.model == "cosy-first"
    assert second_by_name[AgentName.VOICE].tts_service.config.model == "cosy-second"
```

- [ ] **Step 5: Run backend/API tests**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_backend/test_factory.py tests/test_backend/test_main.py tests/test_api/test_routes.py -q
```

Expected: PASS; existing API schemas and resume behavior remain compatible.

- [ ] **Step 6: Commit live resume reload**

```powershell
git add backend/api/routes.py backend/main.py tests/test_api/test_routes.py tests/test_backend/test_factory.py tests/test_backend/test_main.py
git commit -m "feat(api): reload provider config on resume"
```

## Task 9: Quota-free full graph acceptance and documentation

**Files:**

- Modify: `tests/test_e2e/test_end_to_end.py`
- Modify: `PROJECT_SPEC.md`
- Modify: `docs/api.md`

- [ ] **Step 1: Strengthen E2E graph assertions**

Keep local synthetic services. Add synchronization events or call timestamps only inside those local services, then assert:

```python
assert result.status == JobStatus.COMPLETED
assert set(result.agent_results) == {
    AgentName.DIRECTOR,
    AgentName.RESEARCH,
    AgentName.SCRIPT,
    AgentName.STORYBOARD,
    AgentName.VIDEO,
    AgentName.VOICE,
    AgentName.EDITOR,
}
assert llm.generate.call_count == 3
assert len(video_service.calls) == 1
research = ResearchNotes.model_validate(
    result.agent_results[AgentName.RESEARCH].output_data
)
assert research.notes == []
```

The graph-specific barrier test already proves concurrency, so do not make media E2E timing-sensitive.

- [ ] **Step 2: Add local resume acceptance test**

Add these imports:

```python
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from models.research import ResearchNotes
from models.scene import Scene
from models.script import Script
from models.storyboard import Shot, Storyboard
from models.video import VideoOutput
from workflow.resume import resume_job
```

Add a local failure service:

```python
class SelectiveLocalVideoService(LocalVideoService):
    def __init__(self, executable: str, fail_name: str | None = None):
        super().__init__(executable)
        self.fail_name = fail_name
        self.attempted: list[str] = []

    def generate(self, prompt: str, output_path: str) -> str:
        name = Path(output_path).name
        self.attempted.append(name)
        if name == self.fail_name:
            raise RuntimeError("video quota exhausted")
        return super().generate(prompt, output_path)
```

Add the upstream state helper:

```python
def _asset_resume_context() -> WorkflowState:
    context = WorkflowState(job_id="asset-resume", prompt="two shots")
    values = {
        AgentName.DIRECTOR: CreativeBrief(
            title="T",
            prompt="two shots",
            tone="clear",
            audience="general",
            duration_seconds=5,
            summary="S",
            requested_scene_count=1,
            requested_shot_count=2,
            requires_research=False,
        ),
        AgentName.RESEARCH: ResearchNotes(
            brief_summary="skipped",
            notes=[],
            overall_confidence=0,
        ),
        AgentName.SCRIPT: Script(
            title="T",
            scenes=[
                Scene(
                    scene_number=1,
                    narration="One short sentence.",
                    duration_hint=5,
                    visual_direction="Two blue shots",
                )
            ],
        ),
        AgentName.STORYBOARD: Storyboard(
            shots=[
                Shot(
                    shot_number=number,
                    scene_number=1,
                    visual_prompt=f"Blue shot {number}",
                    camera="wide",
                    motion="static",
                    duration=2.5,
                )
                for number in (1, 2)
            ]
        ),
    }
    for name, value in values.items():
        context.agent_results[name] = AgentResult(
            agent_name=name,
            success=True,
            output_data=value.model_dump(mode="json"),
        )
    return context
```

Add the acceptance test:

```python
def test_partial_asset_job_resumes_only_missing_video(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    output_root = Path("outputs")
    storage = LocalStorage(str(output_root))
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    llm = MagicMock(spec=LLMService)

    def agents(video_service):
        return [
            DirectorAgent(llm, storage),
            ResearchAgent(llm, storage),
            ScriptAgent(llm, storage),
            StoryboardAgent(llm, storage),
            VideoAgent(video_service, storage),
            VoiceAgent(LocalTTSService(executable), storage),
            EditorAgent(
                LocalFFmpegService(executable),
                storage,
                output_root,
            ),
        ]

    first_video = SelectiveLocalVideoService(
        executable,
        fail_name="shot_002.mp4",
    )
    failed = Pipeline(storage).run(
        "asset-resume",
        agents(first_video),
        _asset_resume_context(),
    )

    assert failed.status == JobStatus.FAILED
    assert AgentName.VOICE in failed.agent_results
    partial = VideoOutput.model_validate(
        storage.load("asset-resume", "video", "video_output.json")
    )
    assert [clip.shot_number for clip in partial.clips] == [1]

    resumed_video = SelectiveLocalVideoService(executable)
    resumed = resume_job(
        "asset-resume",
        agents(resumed_video),
        storage,
    )

    assert resumed.status == JobStatus.COMPLETED
    assert resumed_video.attempted == ["shot_002.mp4"]
    final_path = Path(
        resumed.agent_results[AgentName.EDITOR].output_data["final_path"]
    )
    assert final_path.is_file()
```

This test uses only fixed LLM state and local FFmpeg media. Assert:

```python
assert failed.status == JobStatus.FAILED
assert AgentName.VOICE in failed.agent_results
assert resumed.status == JobStatus.COMPLETED
assert resumed_video.attempted == ["shot_002.mp4"]
assert final_path.is_file()
```

No network service may appear in this test.

- [ ] **Step 3: Run E2E tests**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_e2e/test_end_to_end.py -q
```

Expected: PASS with no external API calls.

- [ ] **Step 4: Update project and API docs**

In `PROJECT_SPEC.md`, mark all Phase 5 checklist items complete except approval gates, and replace that item with the implemented quota-safe conditional routing wording:

```markdown
- [x] Model the pipeline as a LangGraph state graph.
- [x] Migrate sequential orchestrator to LangGraph nodes.
- [x] Add quota-safe conditional routing and manual-resume failure handling.
- [x] Enable parallel execution of Video + Voice agents.
- [x] Persist individual Video/Voice assets for quota-safe resume.
- [x] Reload provider configuration when resuming a job.
```

In `docs/api.md`, extend resume behavior:

```markdown
The resume request rereads `.env`, rebuilds provider clients, skips completed
agents and valid per-asset manifest entries, then runs only missing work. This
allows model or API-key changes without restarting the API. Paid providers are
never retried automatically.
```

- [ ] **Step 5: Run all focused Phase 5 tests**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agents/test_video.py tests/test_agents/test_voice.py tests/test_workflow/test_graph.py tests/test_workflow/test_pipeline.py tests/test_workflow/test_resume.py tests/test_backend/test_factory.py tests/test_backend/test_main.py tests/test_api/test_routes.py tests/test_e2e/test_end_to_end.py -q
```

Expected: exit code 0 with zero failures and no external calls.

- [ ] **Step 6: Run full quota-free suite and static checks**

```powershell
.\venv\Scripts\python.exe -m pytest -q
git diff --check
rg "langgraph|build_pipeline_graph|video_output.json|voice_output.json|agent_factory" workflow agents backend tests requirements.txt
git status --short
```

Expected:

- full suite passes;
- `git diff --check` emits nothing;
- search shows graph/factory/manifest coverage;
- only intended implementation and documentation files are changed.

- [ ] **Step 7: Commit acceptance and docs**

```powershell
git add tests/test_e2e/test_end_to_end.py PROJECT_SPEC.md docs/api.md
git commit -m "docs: complete Phase 5 LangGraph migration"
```

## Manual smoke test (optional and paid)

Do not run during implementation. After all quota-free verification passes, the user may run:

```powershell
.\venv\Scripts\python.exe .\run_test.py
```

For resume-model switching:

1. Start a job that fails from quota or provider configuration.
2. Confirm successful clip/track entries exist in `video_output.json` or `voice_output.json`.
3. Edit only the needed model/API values in `.env`.
4. Call `POST /resume/{job_id}` without restarting the API.
5. Confirm completed manifest entries were not regenerated and final MP4 exists.

Acceptance remains one demo job; concurrent user jobs and background execution are not tested or supported in Phase 5.
