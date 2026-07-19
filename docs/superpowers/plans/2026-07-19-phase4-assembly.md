# Phase 4 Assembly Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the sequential seven-agent MVP by assembling ordered video clips and per-scene narration into a downloadable 1280×720 MP4, with working resume/status behavior and quota-free end-to-end coverage.

**Architecture:** `EditorAgent` maps typed Storyboard, Video, and Voice results into ordered `SceneMedia` values and delegates all media work to an injected `FFmpegService`. `LocalFFmpegService` uses a bundled `imageio-ffmpeg` executable to render narration-led temporary scene files and concatenate them with hard cuts; API routes expose the exact final artifact and execute the existing resume workflow.

**Tech Stack:** Python 3.12, Pydantic 2, FastAPI, `imageio-ffmpeg`, FFmpeg subprocesses, pytest, FastAPI TestClient.

---

## File Map

| File | Responsibility |
| --- | --- |
| `models/editor.py` | Typed `SceneMedia` service input and `EditorOutput` agent result. |
| `tools/ffmpeg.py` | FFmpeg interface, bundled executable discovery, per-scene rendering, final concatenation, and process errors. |
| `agents/editor.py` | Upstream validation, storyboard ordering, service call, persistence, and artifact registration. |
| `backend/main.py` | Construct FFmpeg service and append Editor as agent seven. |
| `backend/api/schemas.py` | Add final-video download URL to result metadata. |
| `backend/api/routes.py` | Exact Editor result, MP4 download, and real resume execution. |
| `requirements.txt` | Supply the FFmpeg executable through `imageio-ffmpeg`. |
| `tests/test_models/test_editor.py` | Contract validation. |
| `tests/test_tools/test_ffmpeg.py` | Command construction, failures, and local binary integration. |
| `tests/test_agents/test_editor.py` | Editor mapping, validation, persistence, and service interaction. |
| `tests/test_api/test_routes.py` | Result/download/resume route behavior. |
| `tests/test_backend/test_main.py` | Seven-agent production wiring. |
| `tests/test_e2e/test_end_to_end.py` | Quota-free seven-agent prompt-to-MP4 journey. |
| `tests/test_workflow/test_resume.py` | Resume specifically from Editor failure. |

---

### Task 1: Define the Editor contracts

**Files:**

- Create: `models/editor.py`
- Create: `tests/test_models/test_editor.py`

- [ ] **Step 1: Write the failing contract tests**

```python
from pydantic import ValidationError
import pytest

from models.editor import EditorOutput, SceneMedia


def test_scene_media_requires_at_least_one_clip():
    with pytest.raises(ValidationError):
        SceneMedia(scene_number=1, clip_paths=[], narration_path="voice.mp3")


def test_scene_media_accepts_ordered_clips():
    media = SceneMedia(
        scene_number=2,
        clip_paths=["shot_002.mp4", "shot_003.mp4"],
        narration_path="scene_002.mp3",
    )
    assert media.clip_paths == ["shot_002.mp4", "shot_003.mp4"]


def test_editor_output_records_final_path_and_scene_count():
    output = EditorOutput(final_path="outputs/job/editor/final/final_video.mp4", scene_count=2)
    assert output.scene_count == 2


def test_editor_output_rejects_zero_scenes():
    with pytest.raises(ValidationError):
        EditorOutput(final_path="final.mp4", scene_count=0)
```

- [ ] **Step 2: Run the contract tests and confirm the missing-module failure**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_models/test_editor.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'models.editor'`.

- [ ] **Step 3: Implement the contracts**

Create `models/editor.py`:

```python
"""Editor Agent input and output models."""

from pydantic import BaseModel, Field


class SceneMedia(BaseModel):
    """Ordered visual clips and one narration track for a scene."""

    scene_number: int = Field(ge=1)
    clip_paths: list[str] = Field(min_length=1)
    narration_path: str = Field(min_length=1)


class EditorOutput(BaseModel):
    """Final media produced by the Editor Agent."""

    final_path: str = Field(min_length=1)
    scene_count: int = Field(ge=1)
```

- [ ] **Step 4: Run the contract tests**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_models/test_editor.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit the contracts**

```powershell
git add models/editor.py tests/test_models/test_editor.py
git commit -m "feat: define editor media contracts"
```

---

### Task 2: Implement the local FFmpeg assembly service

**Files:**

- Modify: `requirements.txt`
- Modify: `tools/ffmpeg.py`
- Create: `tests/test_tools/test_ffmpeg.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/test_tools/test_ffmpeg.py` with a recording subclass for unit behavior and one marked local integration test:

```python
from pathlib import Path
import subprocess

import imageio_ffmpeg
import pytest

from models.editor import SceneMedia
from tools.ffmpeg import FFmpegError, LocalFFmpegService


class RecordingFFmpegService(LocalFFmpegService):
    def __init__(self):
        super().__init__(executable="ffmpeg-test")
        self.commands: list[list[str]] = []

    def _run(self, command: list[str], operation: str) -> None:
        self.commands.append(command)
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_bytes(b"media")


def _inputs(tmp_path: Path) -> list[SceneMedia]:
    clip = tmp_path / "shot.mp4"
    audio = tmp_path / "scene.mp3"
    clip.write_bytes(b"clip")
    audio.write_bytes(b"audio")
    return [SceneMedia(scene_number=1, clip_paths=[str(clip)], narration_path=str(audio))]


def test_assemble_renders_scene_with_narration_and_writes_final(tmp_path):
    service = RecordingFFmpegService()
    output = tmp_path / "final" / "final_video.mp4"
    result = service.assemble(_inputs(tmp_path), str(output))
    assert result == str(output)
    assert output.read_bytes() == b"media"
    scene_command = service.commands[0]
    assert "-shortest" in scene_command
    assert any("tpad=stop_mode=clone" in value for value in scene_command)


def test_assemble_rejects_missing_input_file(tmp_path):
    service = RecordingFFmpegService()
    scene = SceneMedia(
        scene_number=1,
        clip_paths=[str(tmp_path / "missing.mp4")],
        narration_path=str(tmp_path / "missing.mp3"),
    )
    with pytest.raises(FileNotFoundError, match="missing.mp4"):
        service.assemble([scene], str(tmp_path / "final.mp4"))


def test_run_translates_nonzero_exit(monkeypatch):
    service = LocalFFmpegService(executable="ffmpeg-test")
    completed = subprocess.CompletedProcess(["ffmpeg-test"], 1, "", "bad codec")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)
    with pytest.raises(FFmpegError, match="bad codec"):
        service._run(["ffmpeg-test", "-version"], "probe")


def test_bundled_ffmpeg_creates_real_mp4(tmp_path):
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    clip = tmp_path / "clip.mp4"
    audio = tmp_path / "voice.mp3"
    subprocess.run(
        [executable, "-y", "-f", "lavfi", "-i", "color=c=blue:s=1280x720:d=0.4",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)],
        check=True, capture_output=True, text=True,
    )
    subprocess.run(
        [executable, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.6",
         "-q:a", "4", str(audio)],
        check=True, capture_output=True, text=True,
    )
    output = tmp_path / "final.mp4"
    service = LocalFFmpegService(executable=executable)
    service.assemble(
        [SceneMedia(scene_number=1, clip_paths=[str(clip)], narration_path=str(audio))],
        str(output),
    )
    assert output.exists()
    assert output.stat().st_size > 1_000
```

- [ ] **Step 2: Add the executable dependency and verify the service tests fail for the empty module**

Replace the media dependency in `requirements.txt` with:

```text
# ---- Media Processing ----
imageio-ffmpeg>=0.6
```

Install only after the requirement is recorded:

```powershell
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pytest tests/test_tools/test_ffmpeg.py -v
```

Expected: tests fail because `FFmpegError` and `LocalFFmpegService` are absent.

- [ ] **Step 3: Implement FFmpeg discovery, rendering, and concatenation**

Replace `tools/ffmpeg.py` with:

```python
"""FFmpeg-based assembly for the Editor Agent."""

from abc import ABC, abstractmethod
from pathlib import Path
import shutil
import subprocess
import tempfile

import imageio_ffmpeg

from models.editor import SceneMedia


class FFmpegError(RuntimeError):
    """Raised when local media assembly fails."""


class FFmpegService(ABC):
    @abstractmethod
    def assemble(self, scenes: list[SceneMedia], output_path: str) -> str:
        """Assemble ordered scene media into one MP4."""
        ...


class LocalFFmpegService(FFmpegService):
    """Render narration-led 1280x720 scene segments with a local FFmpeg binary."""

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or imageio_ffmpeg.get_ffmpeg_exe()

    def assemble(self, scenes: list[SceneMedia], output_path: str) -> str:
        if not scenes:
            raise ValueError("FFmpeg assembly requires at least one scene")
        self._validate_inputs(scenes)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="assembly-", dir=output.parent) as temp_name:
            temp_dir = Path(temp_name)
            rendered = []
            for index, scene in enumerate(scenes, start=1):
                scene_path = temp_dir / f"scene_{index:03d}.mp4"
                self._render_scene(scene, scene_path)
                rendered.append(scene_path)
            self._concat_scenes(rendered, output)

        if not output.is_file() or output.stat().st_size == 0:
            raise FFmpegError(f"FFmpeg did not create a non-empty output: {output}")
        return str(output)

    @staticmethod
    def _validate_inputs(scenes: list[SceneMedia]) -> None:
        for scene in scenes:
            for raw_path in [*scene.clip_paths, scene.narration_path]:
                path = Path(raw_path)
                if not path.is_file():
                    raise FileNotFoundError(f"Editor input file does not exist: {path}")

    def _render_scene(self, scene: SceneMedia, output: Path) -> None:
        command = [self.executable, "-y"]
        for clip_path in scene.clip_paths:
            command.extend(["-i", clip_path])
        audio_index = len(scene.clip_paths)
        command.extend(["-i", scene.narration_path])

        normalized = []
        filters = []
        video_filter = (
            "scale=1280:720:force_original_aspect_ratio=decrease,"
            "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,setpts=PTS-STARTPTS"
        )
        for index in range(len(scene.clip_paths)):
            label = f"v{index}"
            filters.append(f"[{index}:v:0]{video_filter}[{label}]")
            normalized.append(f"[{label}]")
        if len(normalized) == 1:
            filters.append(
                f"{normalized[0]}tpad=stop_mode=clone:stop_duration=3600[scene_v]"
            )
        else:
            filters.append(
                f"{''.join(normalized)}concat=n={len(normalized)}:v=1:a=0[joined_v]"
            )
            filters.append("[joined_v]tpad=stop_mode=clone:stop_duration=3600[scene_v]")
        filters.append(
            f"[{audio_index}:a:0]aresample=48000,"
            "aformat=sample_fmts=fltp:channel_layouts=stereo,"
            "asetpts=PTS-STARTPTS[scene_a]"
        )

        command.extend(
            [
                "-filter_complex", ";".join(filters),
                "-map", "[scene_v]", "-map", "[scene_a]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
                "-c:a", "aac", "-ar", "48000", "-ac", "2",
                "-shortest", "-movflags", "+faststart", str(output),
            ]
        )
        self._run(command, f"render scene {scene.scene_number}")

    def _concat_scenes(self, scene_paths: list[Path], output: Path) -> None:
        if len(scene_paths) == 1:
            shutil.copy2(scene_paths[0], output)
            return
        command = [self.executable, "-y"]
        for scene_path in scene_paths:
            command.extend(["-i", str(scene_path)])
        streams = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(len(scene_paths)))
        command.extend(
            [
                "-filter_complex",
                f"{streams}concat=n={len(scene_paths)}:v=1:a=1[final_v][final_a]",
                "-map", "[final_v]", "-map", "[final_a]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
                "-c:a", "aac", "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart", str(output),
            ]
        )
        self._run(command, "concatenate scenes")

    def _run(self, command: list[str], operation: str) -> None:
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError as exc:
            raise FFmpegError(f"Unable to launch FFmpeg for {operation}: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip()[-2000:] or "no stderr output"
            raise FFmpegError(f"FFmpeg failed to {operation}: {detail}")
```

- [ ] **Step 4: Run all FFmpeg service tests**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_tools/test_ffmpeg.py -v
```

Expected: 4 passed and no network calls.

- [ ] **Step 5: Commit the FFmpeg service**

```powershell
git add requirements.txt tools/ffmpeg.py tests/test_tools/test_ffmpeg.py
git commit -m "feat: add local FFmpeg assembly service"
```

---

### Task 3: Implement Editor Agent mapping and persistence

**Files:**

- Modify: `agents/editor.py`
- Modify: `tests/test_agents/test_editor.py`

- [ ] **Step 1: Write failing Editor tests**

Create helpers that build a context containing a storyboard with two shots in scene 1 and one shot in scene 2, matching `VideoOutput`, and matching `VoiceOutput`. Write these behaviors in `tests/test_agents/test_editor.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.editor import EditorAgent
from models.agent_result import AgentResult
from models.editor import EditorOutput
from models.enums import AgentName
from models.storyboard import Shot, Storyboard
from models.video import VideoClip, VideoOutput
from models.voice import AudioTrack, VoiceOutput
from models.workflow_state import WorkflowState
from storage.local import LocalStorage
from tools.ffmpeg import FFmpegService


def _context(tmp_path: Path) -> WorkflowState:
    clip_paths = []
    for number in (1, 2, 3):
        path = tmp_path / f"shot_{number:03d}.mp4"
        path.write_bytes(b"clip")
        clip_paths.append(str(path))
    track_paths = []
    for number in (1, 2):
        path = tmp_path / f"scene_{number:03d}.mp3"
        path.write_bytes(b"audio")
        track_paths.append(str(path))

    state = WorkflowState(job_id="editor-job", prompt="test")
    storyboard = Storyboard(shots=[
        Shot(shot_number=1, scene_number=1, visual_prompt="a", camera="wide", motion="pan", duration=5),
        Shot(shot_number=2, scene_number=1, visual_prompt="b", camera="wide", motion="pan", duration=5),
        Shot(shot_number=3, scene_number=2, visual_prompt="c", camera="wide", motion="pan", duration=5),
    ])
    video = VideoOutput(clips=[
        VideoClip(shot_number=i, file_path=clip_paths[i - 1], duration=5) for i in (1, 2, 3)
    ])
    voice = VoiceOutput(tracks=[
        AudioTrack(scene_number=i, file_path=track_paths[i - 1], duration=5) for i in (1, 2)
    ])
    for name, value in ((AgentName.STORYBOARD, storyboard), (AgentName.VIDEO, video), (AgentName.VOICE, voice)):
        state.agent_results[name] = AgentResult(
            agent_name=name, success=True, output_data=value.model_dump(mode="json")
        )
    return state


def _service(tmp_path: Path) -> MagicMock:
    service = MagicMock(spec=FFmpegService)
    def assemble(scenes, output_path):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"final")
        return output_path
    service.assemble.side_effect = assemble
    return service


def test_editor_groups_clips_by_scene_in_storyboard_order(tmp_path):
    service = _service(tmp_path)
    agent = EditorAgent(service, output_dir=tmp_path / "outputs")
    agent.run(_context(tmp_path))
    scenes = service.assemble.call_args.args[0]
    assert [scene.scene_number for scene in scenes] == [1, 2]
    assert len(scenes[0].clip_paths) == 2
    assert len(scenes[1].clip_paths) == 1


def test_editor_writes_result_metadata_and_artifact(tmp_path):
    storage = LocalStorage(str(tmp_path / "outputs"))
    state = _context(tmp_path)
    result = EditorAgent(
        _service(tmp_path), storage=storage, output_dir=tmp_path / "outputs"
    ).run(state)
    output = EditorOutput.model_validate(result.agent_results[AgentName.EDITOR].output_data)
    assert Path(output.final_path).read_bytes() == b"final"
    assert output.scene_count == 2
    artifact = result.agent_results[AgentName.EDITOR].artifacts[0]
    assert artifact.filename == "final/final_video.mp4"
    assert storage.exists("editor-job", "editor", "editor_output.json")


@pytest.mark.parametrize("missing", [AgentName.STORYBOARD, AgentName.VIDEO, AgentName.VOICE])
def test_editor_rejects_missing_upstream_result(tmp_path, missing):
    state = _context(tmp_path)
    del state.agent_results[missing]
    with pytest.raises(ValueError, match=missing.value):
        EditorAgent(_service(tmp_path), output_dir=tmp_path).run(state)


def test_editor_rejects_missing_shot_clip(tmp_path):
    state = _context(tmp_path)
    state.agent_results[AgentName.VIDEO].output_data["clips"].pop()
    with pytest.raises(ValueError, match="shot 3"):
        EditorAgent(_service(tmp_path), output_dir=tmp_path).run(state)


def test_editor_rejects_missing_scene_narration(tmp_path):
    state = _context(tmp_path)
    state.agent_results[AgentName.VOICE].output_data["tracks"].pop()
    with pytest.raises(ValueError, match="scene 2"):
        EditorAgent(_service(tmp_path), output_dir=tmp_path).run(state)
```

- [ ] **Step 2: Run Editor tests and verify they fail because Editor is absent**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_agents/test_editor.py -v
```

Expected: import fails because `EditorAgent` is absent.

- [ ] **Step 3: Implement Editor Agent**

Replace `agents/editor.py` with:

```python
"""Editor Agent — validates and assembles final narrated media."""

from collections import defaultdict
from pathlib import Path

from models.agent_result import AgentResult, ArtifactRef
from models.editor import EditorOutput, SceneMedia
from models.enums import AgentName
from models.storyboard import Storyboard
from models.video import VideoOutput
from models.voice import VoiceOutput
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from tools.ffmpeg import FFmpegService


class EditorAgent:
    name = AgentName.EDITOR

    def __init__(
        self,
        ffmpeg_service: FFmpegService,
        storage: StorageBackend | None = None,
        output_dir: str | Path = "./outputs",
    ) -> None:
        self.ffmpeg_service = ffmpeg_service
        self.storage = storage
        self.output_dir = Path(output_dir)

    def run(self, context: WorkflowState) -> WorkflowState:
        for required in (AgentName.STORYBOARD, AgentName.VIDEO, AgentName.VOICE):
            if required not in context.agent_results:
                raise ValueError(f"Editor agent requires {required.value} output in context")

        storyboard = Storyboard.model_validate(
            context.agent_results[AgentName.STORYBOARD].output_data
        )
        video = VideoOutput.model_validate(context.agent_results[AgentName.VIDEO].output_data)
        voice = VoiceOutput.model_validate(context.agent_results[AgentName.VOICE].output_data)
        scenes = self._build_scene_media(storyboard, video, voice)

        output_path = self.output_dir / context.job_id / "editor" / "final" / "final_video.mp4"
        final_path = self.ffmpeg_service.assemble(scenes, str(output_path))
        output = EditorOutput(final_path=final_path, scene_count=len(scenes))

        if self.storage is not None:
            self.storage.save(
                context.job_id,
                self.name.value,
                "editor_output.json",
                output.model_dump(mode="json"),
            )
        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data=output.model_dump(mode="json"),
            artifacts=[ArtifactRef(
                agent_name=self.name,
                filename="final/final_video.mp4",
                content_type="video/mp4",
                size_bytes=Path(final_path).stat().st_size,
            )],
        )
        return context

    @staticmethod
    def _unique_by(items: list, attribute: str, label: str) -> dict[int, object]:
        indexed = {}
        for item in items:
            key = getattr(item, attribute)
            if key in indexed:
                raise ValueError(f"Editor received duplicate {label} {key}")
            indexed[key] = item
        return indexed

    def _build_scene_media(
        self, storyboard: Storyboard, video: VideoOutput, voice: VoiceOutput
    ) -> list[SceneMedia]:
        shots = self._unique_by(storyboard.shots, "shot_number", "storyboard shot")
        clips = self._unique_by(video.clips, "shot_number", "video clip for shot")
        tracks = self._unique_by(voice.tracks, "scene_number", "narration for scene")
        missing_clips = sorted(set(shots) - set(clips))
        if missing_clips:
            raise ValueError(f"Editor is missing video clip for shot {missing_clips[0]}")

        grouped: dict[int, list[str]] = defaultdict(list)
        scene_order: list[int] = []
        for shot in storyboard.shots:
            if shot.scene_number not in grouped:
                scene_order.append(shot.scene_number)
            grouped[shot.scene_number].append(clips[shot.shot_number].file_path)

        scenes = []
        for scene_number in scene_order:
            if scene_number not in tracks:
                raise ValueError(f"Editor is missing narration for scene {scene_number}")
            paths = [*grouped[scene_number], tracks[scene_number].file_path]
            missing_files = [path for path in paths if not Path(path).is_file()]
            if missing_files:
                raise FileNotFoundError(f"Editor input file does not exist: {missing_files[0]}")
            scenes.append(SceneMedia(
                scene_number=scene_number,
                clip_paths=grouped[scene_number],
                narration_path=tracks[scene_number].file_path,
            ))
        return scenes
```

- [ ] **Step 4: Run Editor and FFmpeg tests**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_agents/test_editor.py tests/test_tools/test_ffmpeg.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit Editor Agent**

```powershell
git add agents/editor.py tests/test_agents/test_editor.py
git commit -m "feat: implement Editor Agent assembly flow"
```

---

### Task 4: Wire Editor into production and expose the final MP4

**Files:**

- Modify: `backend/main.py`
- Modify: `backend/api/schemas.py`
- Modify: `backend/api/routes.py`
- Modify: `tests/test_api/test_schemas.py`
- Modify: `tests/test_api/test_routes.py`
- Create: `tests/test_backend/test_main.py`

- [ ] **Step 1: Write failing API and production-wiring tests**

Add this helper and these tests to `tests/test_api/test_routes.py` (with imports for `Path`, `AgentResult`, `ArtifactRef`, and `EditorOutput`):

```python
def _complete_with_editor_result(client, storage, job_store, tmp_path):
    response = client.post("/generate", json={"prompt": "test video"})
    job_id = response.json()["job_id"]
    final_path = tmp_path / job_id / "editor" / "final" / "final_video.mp4"
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(b"final-mp4")
    output = EditorOutput(final_path=str(final_path), scene_count=1)
    context = WorkflowState(job_id=job_id, prompt="test video", status=JobStatus.COMPLETED)
    context.agent_results[AgentName.EDITOR] = AgentResult(
        agent_name=AgentName.EDITOR,
        success=True,
        output_data=output.model_dump(mode="json"),
        artifacts=[ArtifactRef(
            agent_name=AgentName.EDITOR,
            filename="final/final_video.mp4",
            content_type="video/mp4",
            size_bytes=9,
        )],
    )
    storage.save(job_id, "pipeline", "context.json", context.model_dump(mode="json"))
    job_store[job_id].status = JobStatus.COMPLETED
    return job_id, final_path


def test_result_returns_exact_final_path_and_download_url(tmp_path):
    client, storage, job_store = _make_test_app()
    job_id, final_path = _complete_with_editor_result(
        client, storage, job_store, tmp_path
    )
    response = client.get(f"/result/{job_id}")
    assert response.json()["output_path"] == str(final_path)
    assert response.json()["download_url"] == f"/result/{job_id}/download"


def test_download_returns_final_mp4(tmp_path):
    client, storage, job_store = _make_test_app()
    job_id, _ = _complete_with_editor_result(client, storage, job_store, tmp_path)
    response = client.get(f"/result/{job_id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("video/mp4")
    assert response.content == b"final-mp4"


def test_download_returns_404_when_final_file_is_missing(tmp_path):
    client, storage, job_store = _make_test_app()
    job_id, final_path = _complete_with_editor_result(
        client, storage, job_store, tmp_path
    )
    final_path.unlink()
    response = client.get(f"/result/{job_id}/download")
    assert response.status_code == 404
```

Update `TestResultResponse` so the expected schema includes:

```python
download_url="/result/abc-123/download"
```

Create `tests/test_backend/test_main.py`:

```python
import backend.main as main_module
from models.enums import AgentName


def test_production_app_includes_editor_as_seventh_agent(monkeypatch):
    captured = {}

    def capture_app(storage, job_store, agents):
        captured["agents"] = agents
        return object()

    monkeypatch.setattr(main_module, "create_app", capture_app)
    main_module.create_production_app()
    assert [agent.name for agent in captured["agents"]] == [
        AgentName.DIRECTOR,
        AgentName.RESEARCH,
        AgentName.SCRIPT,
        AgentName.STORYBOARD,
        AgentName.VIDEO,
        AgentName.VOICE,
        AgentName.EDITOR,
    ]
```

- [ ] **Step 2: Run focused tests and confirm the new fields/routes fail**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_api/test_schemas.py tests/test_api/test_routes.py tests/test_backend/test_main.py -v
```

Expected: failures for missing `download_url`, missing download route, and non-specific output path.

- [ ] **Step 3: Add Editor to production**

In `backend/main.py`, add:

```python
from agents.editor import EditorAgent
from tools.ffmpeg import LocalFFmpegService
```

Construct the service after the existing provider services:

```python
ffmpeg_service = LocalFFmpegService()
```

Append this agent after `VoiceAgent`:

```python
EditorAgent(
    ffmpeg_service=ffmpeg_service,
    storage=storage,
    output_dir=settings.storage.output_dir,
),
```

- [ ] **Step 4: Implement exact result metadata and file download**

Add to `ResultResponse` in `backend/api/schemas.py`:

```python
download_url: str
```

In `backend/api/routes.py`, import:

```python
from pathlib import Path
from fastapi.responses import FileResponse
from models.editor import EditorOutput
from models.enums import AgentName
```

Add a local helper inside `create_app`:

```python
def completed_editor_output(job_id: str) -> EditorOutput:
    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if record.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Job is {record.status.value}, not completed")
    context_data = storage.load(job_id, "pipeline", "context.json")
    if context_data is None:
        raise HTTPException(status_code=404, detail="Job context not found")
    context = WorkflowState.model_validate(context_data)
    editor_result = context.agent_results.get(AgentName.EDITOR)
    if editor_result is None or not editor_result.success:
        raise HTTPException(status_code=404, detail="Final video result not found")
    return EditorOutput.model_validate(editor_result.output_data)
```

Use it in the existing result route and preserve artifact aggregation:

```python
editor_output = completed_editor_output(job_id)
return ResultResponse(
    job_id=record.job_id,
    status=record.status,
    output_path=editor_output.final_path,
    download_url=f"/result/{job_id}/download",
    artifacts=artifacts,
)
```

Add the download route:

```python
@app.get("/result/{job_id}/download")
def download_result(job_id: str) -> FileResponse:
    editor_output = completed_editor_output(job_id)
    final_path = Path(editor_output.final_path)
    if not final_path.is_file():
        raise HTTPException(status_code=404, detail="Final video file not found")
    return FileResponse(
        path=final_path,
        media_type="video/mp4",
        filename="final_video.mp4",
    )
```

- [ ] **Step 5: Run API tests**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_api/test_schemas.py tests/test_api/test_routes.py tests/test_backend/test_main.py -v
```

Expected: all API schema and route tests pass.

- [ ] **Step 6: Commit production and result wiring**

```powershell
git add backend/main.py backend/api/schemas.py backend/api/routes.py tests/test_api/test_schemas.py tests/test_api/test_routes.py tests/test_backend/test_main.py
git commit -m "feat: expose assembled final video"
```

---

### Task 5: Make the resume endpoint execute recovery

**Files:**

- Modify: `backend/api/routes.py`
- Modify: `tests/test_api/test_routes.py`
- Modify: `tests/test_workflow/test_resume.py`

- [ ] **Step 1: Write failing resume tests**

Add these helpers and API tests to `tests/test_api/test_routes.py`:

```python
class CompletingEditor(BaseAgent):
    name = AgentName.EDITOR

    def __init__(self, call_order):
        self.call_order = call_order
        super().__init__()

    def run(self, context):
        self.call_order.append(self.name)
        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data={"final_path": "final.mp4", "scene_count": 1},
        )
        return context


def _failed_editor_job(storage, job_store):
    job_id = "resume-editor-job"
    context = WorkflowState(
        job_id=job_id,
        prompt="test",
        status=JobStatus.FAILED,
        failed_agent=AgentName.EDITOR,
        error="FFmpeg unavailable",
    )
    storage.save(job_id, "pipeline", "context.json", context.model_dump(mode="json"))
    job_store[job_id] = JobRecord(
        job_id=job_id,
        prompt="test",
        status=JobStatus.FAILED,
        failed_agent=AgentName.EDITOR,
        error="FFmpeg unavailable",
    )
    return job_id


def test_resume_executes_remaining_agents_and_updates_job_status():
    storage = InMemoryStorage()
    job_store = {}
    call_order = []
    app = create_app(
        storage=storage,
        job_store=job_store,
        agents=[CompletingEditor(call_order)],
    )
    client = TestClient(app)
    job_id = _failed_editor_job(storage, job_store)
    response = client.post(f"/resume/{job_id}")
    assert response.status_code == 202
    assert call_order == [AgentName.EDITOR]
    assert job_store[job_id].status == JobStatus.COMPLETED
    assert job_store[job_id].failed_agent is None
    assert job_store[job_id].error is None


def test_resume_returns_503_without_configured_agents():
    storage = InMemoryStorage()
    job_store = {}
    app = create_app(storage=storage, job_store=job_store)
    client = TestClient(app)
    job_id = _failed_editor_job(storage, job_store)
    response = client.post(f"/resume/{job_id}")
    assert response.status_code == 503
```

Add this workflow test to `tests/test_workflow/test_resume.py` using its existing `StubAgent`, `ALL_AGENTS`, and helpers:

```python
def test_resume_after_editor_failure_skips_all_upstream_agents(tmp_path):
    storage = LocalStorage(str(tmp_path))
    first_agents = _make_stub_agents(ALL_AGENTS, should_fail=AgentName.EDITOR)
    initial = WorkflowState(job_id="editor-retry", prompt="test")
    failed = Pipeline(storage).run("editor-retry", first_agents, initial)
    assert failed.failed_agent == AgentName.EDITOR

    call_order = []
    retry_agents = _make_stub_agents(ALL_AGENTS, call_order=call_order)
    resumed = resume_job("editor-retry", retry_agents, storage)
    assert call_order == [AgentName.EDITOR]
    assert resumed.status == JobStatus.COMPLETED
```

Add `from workflow.pipeline import Pipeline` to that test module.

- [ ] **Step 2: Run resume tests and verify the no-op behavior fails**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_api/test_routes.py -k resume -v
venv\Scripts\python.exe -m pytest tests/test_workflow/test_resume.py -v
```

Expected: the API execution/status assertion fails because the route currently only returns the job ID.

- [ ] **Step 3: Execute `resume_job` and synchronize the record**

Import in `backend/api/routes.py`:

```python
from workflow.resume import resume_job
```

Replace the resume route's final return with:

```python
if not agents:
    raise HTTPException(status_code=503, detail="Resume is unavailable: no agents configured")
context = resume_job(job_id, agents, storage)
record.status = context.status
record.updated_at = context.updated_at
record.failed_agent = context.failed_agent
record.error = context.error
return ResumeResponse(job_id=job_id)
```

- [ ] **Step 4: Run resume and pipeline tests**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_api/test_routes.py -k resume -v
venv\Scripts\python.exe -m pytest tests/test_workflow/test_resume.py tests/test_workflow/test_pipeline.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit resume recovery**

```powershell
git add backend/api/routes.py tests/test_api/test_routes.py tests/test_workflow/test_resume.py
git commit -m "fix: execute pipeline recovery from resume endpoint"
```

---

### Task 6: Add a quota-free seven-agent prompt-to-MP4 test

**Files:**

- Modify: `tests/test_e2e/test_end_to_end.py`

- [ ] **Step 1: Write the full local end-to-end test**

Replace `tests/test_e2e/test_end_to_end.py` with this complete local pipeline test:

```python
from pathlib import Path
import subprocess
from unittest.mock import MagicMock

import imageio_ffmpeg

from agents.director import DirectorAgent
from agents.editor import EditorAgent
from agents.research import ResearchAgent
from agents.script import ScriptAgent
from agents.storyboard import StoryboardAgent
from agents.video import VideoAgent
from agents.voice import VoiceAgent
from models.editor import EditorOutput
from models.enums import AgentName, JobStatus
from models.workflow_state import WorkflowState
from storage.local import LocalStorage
from tools.ffmpeg import LocalFFmpegService
from tools.llm import LLMService
from tools.tts import TTSService
from tools.video_gen import VideoGenService
from workflow.pipeline import Pipeline


class LocalVideoService(VideoGenService):
    def __init__(self, executable: str):
        self.executable = executable

    def generate(self, prompt: str, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                self.executable, "-y", "-f", "lavfi", "-i",
                "color=c=blue:s=1280x720:d=0.4",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return str(path)


class LocalTTSService(TTSService):
    def __init__(self, executable: str):
        self.executable = executable

    def synthesize(self, text: str, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                self.executable, "-y", "-f", "lavfi", "-i",
                "sine=frequency=440:duration=0.6", "-q:a", "4", str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return str(path)


def test_prompt_runs_all_seven_agents_and_produces_mp4(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output_root = tmp_path / "outputs"
    storage = LocalStorage(str(output_root))
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    llm = MagicMock(spec=LLMService)
    llm.generate.side_effect = [
        '{"title":"AI","prompt":"Explain AI briefly","tone":"clear","audience":"general","duration_seconds":1.0,"summary":"AI summary"}',
        '{"brief_summary":"AI summary","notes":[],"overall_confidence":0.8}',
        '{"title":"AI","scenes":[{"scene_number":1,"narration":"AI helps people solve problems.","duration_hint":0.6,"visual_direction":"Blue technology background"}]}',
        '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"Blue technology background","camera":"wide","motion":"static","duration":0.4}]}',
    ]
    agents = [
        DirectorAgent(llm_service=llm, storage=storage),
        ResearchAgent(llm_service=llm, storage=storage),
        ScriptAgent(llm_service=llm, storage=storage),
        StoryboardAgent(llm_service=llm, storage=storage),
        VideoAgent(video_service=LocalVideoService(executable), storage=storage),
        VoiceAgent(tts_service=LocalTTSService(executable), storage=storage),
        EditorAgent(
            ffmpeg_service=LocalFFmpegService(executable),
            storage=storage,
            output_dir=output_root,
        ),
    ]
    state = WorkflowState(job_id="e2e-job", prompt="Explain AI briefly")
    pipeline = Pipeline(storage)
    result = pipeline.run("e2e-job", agents, state)

    assert result.status == JobStatus.COMPLETED
    assert list(result.agent_results) == [
        AgentName.DIRECTOR,
        AgentName.RESEARCH,
        AgentName.SCRIPT,
        AgentName.STORYBOARD,
        AgentName.VIDEO,
        AgentName.VOICE,
        AgentName.EDITOR,
    ]
    editor = EditorOutput.model_validate(result.agent_results[AgentName.EDITOR].output_data)
    final_path = Path(editor.final_path)
    assert final_path.is_file()
    assert final_path.stat().st_size > 1_000
```

The local doubles must invoke only the bundled FFmpeg executable and must not import or construct DashScope services.

- [ ] **Step 2: Run the new E2E test and verify the initial failure**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_e2e/test_end_to_end.py -v
```

Expected before Tasks 1–5 are complete: failure at the missing Editor/FFmpeg path. Expected after implementation: 1 passed with no network calls.

- [ ] **Step 3: Commit the quota-free E2E test**

```powershell
git add tests/test_e2e/test_end_to_end.py
git commit -m "test: cover quota-free prompt to final MP4 flow"
```

---

### Task 7: Document, verify, and mark Phase 4 complete only with evidence

**Files:**

- Modify: `PROJECT_SPEC.md`
- Modify: `README.md`
- Modify: `docs/agent-contracts.md`
- Modify: `docs/api.md`

- [ ] **Step 1: Document the final contract and safe testing commands**

Update the Phase 4 checklist only after every focused test is green. Document:

- Editor inputs (`Storyboard`, `VideoOutput`, `VoiceOutput`) and `EditorOutput`.
- Narration-led timing and hard-cut behavior.
- Exact final path and download route.
- `imageio-ffmpeg` bundled executable behavior.
- `venv\Scripts\python.exe -m pytest tests/ -v` as the quota-free suite.
- `run_test.py` as an opt-in paid live smoke test that is never part of routine verification.

- [ ] **Step 2: Run syntax compilation**

Run:

```powershell
venv\Scripts\python.exe -m compileall agents backend models storage tools workflow tests
```

Expected: exit code 0 with no syntax errors.

- [ ] **Step 3: Run focused Phase 4 tests**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/test_models/test_editor.py tests/test_tools/test_ffmpeg.py tests/test_agents/test_editor.py tests/test_workflow/test_resume.py tests/test_api/test_routes.py tests/test_e2e/test_end_to_end.py -v
```

Expected: all selected tests pass, with no outbound model calls.

- [ ] **Step 4: Run the complete quota-free suite**

Run:

```powershell
venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: exit code 0 and zero failures. Do not run `run_test.py` during automated verification.

- [ ] **Step 5: Inspect the final diff for scope and secrets**

Run:

```powershell
git status --short
git diff --check
git diff -- PROJECT_SPEC.md README.md requirements.txt agents/editor.py tools/ffmpeg.py models/editor.py backend/main.py backend/api/schemas.py backend/api/routes.py tests docs
```

Expected: no whitespace errors, no `.env` content, no generated MP4/MP3 artifacts, and no unrelated changes.

- [ ] **Step 6: Commit Phase 4 documentation**

```powershell
git add PROJECT_SPEC.md README.md docs/agent-contracts.md docs/api.md
git commit -m "docs: complete Phase 4 assembly guidance"
```

---

## Self-Review

### Phase 4 coverage

| Requirement | Covered by |
| --- | --- |
| FFmpeg-based Editor Agent | Tasks 1–3 |
| Prompt to MP4 | Task 6 |
| Resume from failure | Task 5 |
| Basic errors and job status | Tasks 3–5 |
| Narrated stitched MP4 | Tasks 2–3 and 6 |
| Persisted artifacts | Task 3 |
| Final download endpoint | Task 4 |
| Quota-safe testing | Tasks 2, 6, and 7 |

### Type consistency

- `SceneMedia.scene_number`, `clip_paths`, and `narration_path` are used identically by Editor and FFmpeg.
- `EditorOutput.final_path` and `scene_count` are used identically by Editor, API, and tests.
- Editor artifact filename remains relative to the Editor directory: `final/final_video.mp4`.
- The physical output path uses the configured output root: `{output_dir}/{job_id}/editor/final/final_video.mp4`.

### Scope control

The plan deliberately excludes transitions, titles, music, effects, parallel execution, background jobs, duration probing, and live paid-provider verification. Every implementation task contributes directly to the Phase 4 MVP.
