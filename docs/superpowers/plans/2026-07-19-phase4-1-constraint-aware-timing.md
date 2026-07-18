# Phase 4.1 Constraint-Aware Timing Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use test-driven-development for each task and verification-before-completion before each commit.

**Goal:** Enforce explicit scene/shot constraints before paid generation, keep research honest, improve visual prompts, and assemble the final video to storyboard timing instead of short narration timing.

**Architecture:** Add optional constraints to `CreativeBrief`, enforce them once in Script and Storyboard with a single correction call, and keep Research in the seven-agent sequence while allowing a local no-LLM skip. Carry storyboard shot durations through `ClipMedia` into FFmpeg, where clips are trimmed and short audio/video streams are padded to a deterministic scene target.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, `unittest.mock`, imageio-ffmpeg, local FFmpeg filters, existing sequential `Pipeline`.

---

## Constraints and conventions

- Do not call Alibaba, Wan, CosyVoice, or any other paid service from automated tests.
- Keep `longqiang_v3` and the existing provider/model configuration unchanged.
- Use one correction LLM call at most. Invalid JSON still fails immediately; only a valid response that violates a deterministic constraint gets corrected.
- Use `math.isclose(actual, expected, rel_tol=0.10, abs_tol=0.25)` for per-scene storyboard duration validation.
- Preserve the existing seven-agent order. Research skip creates a normal successful `AgentResult` and artifact.
- Commit after each task so the implementation history follows the phases below.

## Task 1: Carry explicit production constraints in the Creative Brief

**Files:**

- Modify: `models/brief.py`
- Modify: `agents/director.py`
- Modify: `tests/test_agents/test_director.py`

### Step 1: Write failing Director tests

Add tests that parse and persist the new fields:

```python
def test_run_stores_explicit_counts_and_research_requirement():
    brief_json = (
        '{"title":"Voxel clip","prompt":"Make exactly one scene and one shot",'
        '"tone":"playful","audience":"general","duration_seconds":5.0,'
        '"summary":"A voxel reveal","requested_scene_count":1,'
        '"requested_shot_count":1,"requires_research":false}'
    )
    agent = DirectorAgent(llm_service=_mock_llm_service(brief_json))

    result = agent.run(_make_context("Make exactly one scene and one shot"))

    brief = CreativeBrief.model_validate(
        result.agent_results[AgentName.DIRECTOR].output_data
    )
    assert brief.requested_scene_count == 1
    assert brief.requested_shot_count == 1
    assert brief.requires_research is False


def test_prompt_tells_director_not_to_invent_counts():
    mock_llm = _mock_llm_service(
        '{"title":"T","prompt":"P","tone":"clear","audience":"general",'
        '"duration_seconds":5,"summary":"S"}'
    )
    DirectorAgent(mock_llm).run(_make_context("Make a short clip"))

    prompt = mock_llm.generate.call_args.args[0]
    assert "only when the user states" in prompt
    assert "requires_research" in prompt
```

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agents/test_director.py -q
```

Expected: FAIL because `CreativeBrief` does not expose the constraint fields and the prompt lacks the new instructions.

### Step 2: Add fields to `CreativeBrief`

Add after `style_keywords`:

```python
requested_scene_count: int | None = Field(default=None, ge=1)
requested_shot_count: int | None = Field(default=None, ge=1)
requires_research: bool = True
```

### Step 3: Extend the Director schema and instructions

Add these keys to `DIRECTOR_PROMPT_TEMPLATE`:

```text
"requested_scene_count": integer or null — copy an exact scene count only when the user states one explicitly,
"requested_shot_count": integer or null — copy an exact total shot count only when the user states one explicitly,
"requires_research": boolean — false for fictional, aesthetic, promotional, or purely creative work; true when factual claims are needed
```

Add a direct rule below the schema:

```text
Do not infer scene or shot counts from duration. Set them only when the user states an exact count. Preserve explicit constraints even if another structure might be more cinematic.
```

### Step 4: Run focused tests

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agents/test_director.py -q
```

Expected: PASS.

### Step 5: Commit Task 1

```powershell
git add models/brief.py agents/director.py tests/test_agents/test_director.py
git commit -m "feat: carry explicit production constraints"
```

## Task 2: Skip unnecessary research and prevent fake verification

**Files:**

- Modify: `agents/research.py`
- Modify: `tests/test_agents/test_research.py`

### Step 1: Write failing Research tests

Change `_make_context_with_brief` to accept `requires_research: bool = True`, then add:

```python
def test_creative_brief_skips_llm_and_emits_empty_notes():
    llm = MagicMock(spec=LLMService)
    result = ResearchAgent(llm).run(
        _make_context_with_brief(requires_research=False)
    )

    llm.generate.assert_not_called()
    notes = ResearchNotes.model_validate(
        result.agent_results[AgentName.RESEARCH].output_data
    )
    assert notes.notes == []
    assert notes.overall_confidence == 0.0
    assert "skipped" in notes.brief_summary.lower()


def test_llm_only_research_cannot_claim_sources_or_verification():
    response = (
        '{"brief_summary":"Facts","notes":[{"topic":"Claim",'
        '"content":"Content","source":"Example University",'
        '"verified":true}],"overall_confidence":0.9}'
    )
    result = ResearchAgent(_mock_llm_service(response)).run(
        _make_context_with_brief(requires_research=True)
    )

    notes = ResearchNotes.model_validate(
        result.agent_results[AgentName.RESEARCH].output_data
    )
    assert notes.notes[0].source is None
    assert notes.notes[0].verified is False
```

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agents/test_research.py -q
```

Expected: FAIL because Research always calls the LLM and trusts its source claims.

### Step 2: Implement local skip and normalization

In `ResearchAgent.run`, branch after validating `brief`:

```python
if not brief.requires_research:
    notes = ResearchNotes(
        brief_summary=f"Research skipped for creative prompt: {brief.summary}",
        notes=[],
        overall_confidence=0.0,
    )
else:
    prompt = RESEARCH_PROMPT_TEMPLATE.format(
        brief_json=brief.model_dump_json()
    )
    raw_response = self.llm_service.generate(prompt, self.name)
    try:
        notes = ResearchNotes.model_validate_json(raw_response)
    except Exception as exc:
        raise ValueError(
            f"Research agent failed to parse LLM response as ResearchNotes: {exc}"
        ) from exc
    notes = notes.model_copy(
        update={
            "notes": [
                note.model_copy(update={"source": None, "verified": False})
                for note in notes.notes
            ]
        }
    )
```

Keep the existing storage and `AgentResult` path shared by both branches.

### Step 3: Update existing assertions

Existing tests that expect `source="Stanford"` or `verified=true` should instead assert the normalized values. The storage test must compare against the normalized `ResearchNotes`, not raw LLM JSON.

### Step 4: Run focused tests

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agents/test_research.py -q
```

Expected: PASS.

### Step 5: Commit Task 2

```powershell
git add agents/research.py tests/test_agents/test_research.py
git commit -m "fix: keep research quota-free and honest"
```

## Task 3: Enforce scene counts with one Script correction

**Files:**

- Modify: `agents/script.py`
- Modify: `tests/test_agents/test_script.py`

### Step 1: Write failing Script correction tests

Allow `_make_context_with_upstream` to accept `requested_scene_count`. Add:

```python
def test_prompt_includes_explicit_scene_count():
    response = (
        '{"title":"T","scenes":[{"scene_number":1,"narration":"N",'
        '"duration_hint":5,"visual_direction":"V"}]}'
    )
    llm = _mock_llm_service(response)
    ScriptAgent(llm).run(_make_context_with_upstream(requested_scene_count=1))

    assert "exactly 1 scene" in llm.generate.call_args_list[0].args[0]


def test_scene_count_mismatch_gets_one_correction():
    two_scenes = (
        '{"title":"T","scenes":['
        '{"scene_number":1,"narration":"A","duration_hint":2.5,"visual_direction":"A"},'
        '{"scene_number":2,"narration":"B","duration_hint":2.5,"visual_direction":"B"}]}'
    )
    one_scene = (
        '{"title":"T","scenes":[{"scene_number":1,"narration":"A",'
        '"duration_hint":5,"visual_direction":"A"}]}'
    )
    llm = MagicMock(spec=LLMService)
    llm.generate.side_effect = [two_scenes, one_scene]

    result = ScriptAgent(llm).run(
        _make_context_with_upstream(requested_scene_count=1)
    )

    assert llm.generate.call_count == 2
    assert len(result.agent_results[AgentName.SCRIPT].output_data["scenes"]) == 1
    assert "exactly 1" in llm.generate.call_args_list[1].args[0]


def test_second_scene_count_mismatch_fails():
    two_scenes = (
        '{"title":"T","scenes":['
        '{"scene_number":1,"narration":"A","duration_hint":2.5,"visual_direction":"A"},'
        '{"scene_number":2,"narration":"B","duration_hint":2.5,"visual_direction":"B"}]}'
    )
    llm = MagicMock(spec=LLMService)
    llm.generate.side_effect = [two_scenes, two_scenes]

    with pytest.raises(ValueError, match="exactly 1 scene"):
        ScriptAgent(llm).run(
            _make_context_with_upstream(requested_scene_count=1)
        )
    assert llm.generate.call_count == 2
```

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agents/test_script.py -q
```

Expected: FAIL because Script does not pass or validate the count.

### Step 2: Add the count rule to the Script prompt

Add `{scene_count_rule}` after the duration rule and format it as:

```python
scene_count_rule = (
    f"Produce exactly {brief.requested_scene_count} scene"
    f"{'s' if brief.requested_scene_count != 1 else ''}."
    if brief.requested_scene_count is not None
    else "Choose the scene count that best fits the brief."
)
```

### Step 3: Add deterministic validation and one correction

Keep parsing small and local:

```python
@staticmethod
def _parse(raw_response: str) -> Script:
    try:
        return Script.model_validate_json(raw_response)
    except Exception as exc:
        raise ValueError(
            f"Script agent failed to parse LLM response as Script: {exc}"
        ) from exc


@staticmethod
def _count_error(script: Script, requested_count: int | None) -> str | None:
    if requested_count is None or len(script.scenes) == requested_count:
        return None
    return (
        f"Script must contain exactly {requested_count} scene"
        f"{'s' if requested_count != 1 else ''}; received {len(script.scenes)}"
    )
```

After the first parse, if `_count_error` returns text, call `generate` once with:

```python
correction_prompt = (
    f"{prompt}\n\nYour previous JSON violated this constraint: {error}. "
    "Return a corrected complete Script JSON object only."
)
```

Parse once more. If the same validation still fails, raise `ValueError(error)` before storing an artifact.

### Step 4: Run focused tests

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agents/test_script.py -q
```

Expected: PASS.

### Step 5: Commit Task 3

```powershell
git add agents/script.py tests/test_agents/test_script.py
git commit -m "feat: enforce explicit scene counts"
```

## Task 4: Enforce Storyboard contracts and improve generation prompts

**Files:**

- Modify: `agents/storyboard.py`
- Modify: `tests/test_agents/test_storyboard.py`

### Step 1: Write failing Storyboard tests

Add tests for the new upstream requirement and prompt rules:

```python
def test_run_requires_director_output():
    ctx = _make_context_with_upstream()
    del ctx.agent_results[AgentName.DIRECTOR]

    with pytest.raises(ValueError, match="Director"):
        StoryboardAgent(_mock_llm_service("irrelevant")).run(ctx)


def test_prompt_requests_renderable_voxel_geometry():
    llm = _mock_llm_service(
        '{"shots":[{"shot_number":1,"scene_number":1,'
        '"visual_prompt":"A cubic block","camera":"wide",'
        '"motion":"static","duration":15}]}'
    )
    StoryboardAgent(llm).run(_make_context_with_upstream())

    prompt = llm.generate.call_args.args[0]
    assert "flat pixel textures" in prompt
    assert "no photorealistic foliage" in prompt
    assert "sound instructions" in prompt
```

Add correction/failure tests using `MagicMock.side_effect` for:

- requested one shot, first response has two, corrected response has one;
- requested one shot, both responses have two, then `ValueError`;
- a Script scene has no Storyboard shot, then correction;
- per-scene shot durations are outside `math.isclose(..., rel_tol=0.10, abs_tol=0.25)`, then correction.

The corrected happy-path JSON for one five-second shot is:

```python
one_shot = (
    '{"shots":[{"shot_number":1,"scene_number":1,'
    '"visual_prompt":"A sharp cubic grass-and-soil block, flat pixel textures",'
    '"camera":"wide","motion":"slow orbit","duration":5.0}],'
    '"total_duration":5.0}'
)
```

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agents/test_storyboard.py -q
```

Expected: FAIL because Storyboard does not read the brief, validate structure/timing, or describe prompt restrictions.

### Step 2: Include the Creative Brief and prompt rules

Require Director and Script outputs. Validate the Director result as `CreativeBrief`, then format both `brief_json` and `script_json` into the prompt.

Add these prompt requirements:

```text
Use visible, renderable details only: subject geometry/material, environment, composition, visible action, camera, lighting, and color.
Avoid brand/style-owner names, authenticity claims, texture-resolution claims, sound instructions, and exact frame timing.
For voxel or block-game visuals, explicitly request cubic geometry, flat pixel textures, clean square edges, and no photorealistic foliage.
```

When `requested_shot_count` is set, add: `Produce exactly N total shot(s).`

### Step 3: Add Storyboard validation

Import `math` and add:

```python
@staticmethod
def _constraint_errors(
    storyboard: Storyboard,
    script: Script,
    requested_shot_count: int | None,
) -> list[str]:
    errors: list[str] = []
    if (
        requested_shot_count is not None
        and len(storyboard.shots) != requested_shot_count
    ):
        errors.append(
            f"Storyboard must contain exactly {requested_shot_count} shot"
            f"{'s' if requested_shot_count != 1 else ''}; "
            f"received {len(storyboard.shots)}"
        )
    for scene in script.scenes:
        durations = [
            shot.duration
            for shot in storyboard.shots
            if shot.scene_number == scene.scene_number
        ]
        if not durations:
            errors.append(
                f"Storyboard must cover script scene {scene.scene_number}"
            )
        elif not math.isclose(
            sum(durations),
            scene.duration_hint,
            rel_tol=0.10,
            abs_tol=0.25,
        ):
            errors.append(
                f"Storyboard scene {scene.scene_number} duration must be "
                f"approximately {scene.duration_hint}s; received {sum(durations)}s"
            )
    return errors
```

Parse the first response. When errors exist, make one correction call containing every error joined with `; `. Parse and validate the corrected response once. Raise `ValueError` with the remaining errors if still invalid.

Also reject Storyboard shots whose `scene_number` does not exist in Script by adding a deterministic `unknown scene` error.

### Step 4: Run focused tests

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agents/test_storyboard.py -q
```

Expected: PASS.

### Step 5: Commit Task 4

```powershell
git add agents/storyboard.py tests/test_agents/test_storyboard.py
git commit -m "feat: validate storyboard before generation"
```

## Task 5: Prove constraint failure stops before paid video generation

**Files:**

- Modify: `tests/test_e2e/test_end_to_end.py`

### Step 1: Write the pipeline regression test

Add a zero-network recording service:

```python
class RecordingVideoService(VideoGenService):
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def generate(self, prompt: str, output_path: str) -> str:
        self.calls.append((prompt, output_path))
        raise AssertionError("Video generation must not run")
```

Build a pipeline through Video with:

- Director response requesting one scene and one shot;
- Research skipped with `requires_research=false`;
- Script response containing one scene;
- two Storyboard responses that both contain two shots;
- `VideoAgent` using `RecordingVideoService`.

Assert:

```python
assert result.status == JobStatus.FAILED
assert result.failed_agent == AgentName.STORYBOARD
assert video_service.calls == []
assert AgentName.VIDEO not in result.agent_results
```

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_e2e/test_end_to_end.py -k stops_before_video -q
```

Expected: PASS after Tasks 1-4. This is a new regression lock, not a new runtime implementation.

### Step 2: Commit Task 5

```powershell
git add tests/test_e2e/test_end_to_end.py
git commit -m "test: prevent paid generation after constraint failure"
```

## Task 6: Carry planned shot timing into Editor media contracts

**Files:**

- Modify: `models/editor.py`
- Modify: `agents/editor.py`
- Modify: `tests/test_models/test_editor.py`
- Modify: `tests/test_agents/test_editor.py`

### Step 1: Write failing model and mapping tests

In `tests/test_models/test_editor.py`, add validation tests for:

```python
clip = ClipMedia(
    shot_number=1,
    file_path="shot.mp4",
    planned_duration=0.65,
)
scene = SceneMedia(
    scene_number=1,
    clips=[clip],
    narration_path="scene.mp3",
    planned_duration=0.65,
)
assert scene.clips[0].shot_number == 1
```

Also assert zero/negative planned durations fail Pydantic validation.

In `tests/test_agents/test_editor.py`, inspect `ffmpeg_service.assemble.call_args.args[0]` and assert:

```python
assert [clip.shot_number for clip in scenes[0].clips] == [1, 2]
assert [clip.planned_duration for clip in scenes[0].clips] == [5.0, 5.0]
assert scenes[0].planned_duration == 10.0
assert scenes[1].planned_duration == 5.0
```

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_models/test_editor.py tests/test_agents/test_editor.py -q
```

Expected: FAIL because `ClipMedia` does not exist and `SceneMedia` carries only string paths.

### Step 2: Replace the Editor input model

Implement:

```python
class ClipMedia(BaseModel):
    """One generated clip paired with its Storyboard timing."""

    shot_number: int = Field(ge=1)
    file_path: str = Field(min_length=1)
    planned_duration: float = Field(gt=0)


class SceneMedia(BaseModel):
    """Ordered clips, narration, and planned total for one scene."""

    scene_number: int = Field(ge=1)
    clips: list[ClipMedia] = Field(min_length=1)
    narration_path: str = Field(min_length=1)
    planned_duration: float = Field(gt=0)
```

### Step 3: Map Storyboard shots to `ClipMedia`

Import `ClipMedia`. Group objects instead of paths:

```python
grouped: dict[int, list[ClipMedia]] = defaultdict(list)
for shot in storyboard.shots:
    if shot.scene_number not in grouped:
        scene_order.append(shot.scene_number)
    grouped[shot.scene_number].append(
        ClipMedia(
            shot_number=shot.shot_number,
            file_path=clips[shot.shot_number].file_path,
            planned_duration=shot.duration,
        )
    )
```

Validate `clip.file_path` plus narration, and construct:

```python
SceneMedia(
    scene_number=scene_number,
    clips=grouped[scene_number],
    narration_path=tracks[scene_number].file_path,
    planned_duration=sum(
        clip.planned_duration for clip in grouped[scene_number]
    ),
)
```

### Step 4: Run focused tests

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_models/test_editor.py tests/test_agents/test_editor.py -q
```

Expected: PASS.

### Step 5: Commit Task 6

```powershell
git add models/editor.py agents/editor.py tests/test_models/test_editor.py tests/test_agents/test_editor.py
git commit -m "refactor: carry storyboard timing into editor"
```

## Task 7: Trim clips and pad scenes to deterministic duration

**Files:**

- Modify: `tools/ffmpeg.py`
- Modify: `tests/test_tools/test_ffmpeg.py`

### Step 1: Update fixtures and write failing command tests

Update every `SceneMedia` fixture to use `ClipMedia` and `planned_duration`. Make `RecordingFFmpegService` accept a configurable probe duration:

```python
class RecordingFFmpegService(LocalFFmpegService):
    def __init__(self, narration_duration: float = 1.0):
        super().__init__(executable="ffmpeg-test")
        self.narration_duration = narration_duration
        self.commands: list[list[str]] = []

    def _probe_duration(self, path: Path) -> float:
        return self.narration_duration
```

Add:

```python
def test_render_trims_each_clip_and_uses_planned_duration_when_audio_is_short(tmp_path):
    service = RecordingFFmpegService(narration_duration=1.0)
    scenes = _inputs(tmp_path, planned_duration=2.0)

    service.assemble(scenes, str(tmp_path / "final.mp4"))

    command = service.commands[0]
    filters = command[command.index("-filter_complex") + 1]
    assert "trim=duration=2.000000" in filters
    assert "tpad=stop_mode=clone" in filters
    assert "apad=whole_dur=2.000000" in filters
    assert command[command.index("-t") + 1] == "2.000000"


def test_render_uses_narration_duration_when_audio_is_longer(tmp_path):
    service = RecordingFFmpegService(narration_duration=3.0)
    scenes = _inputs(tmp_path, planned_duration=2.0)

    service.assemble(scenes, str(tmp_path / "final.mp4"))

    command = service.commands[0]
    assert command[command.index("-t") + 1] == "3.000000"
```

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_tools/test_ffmpeg.py -q
```

Expected: FAIL because FFmpeg still uses raw clip lengths and narration as the sole target.

### Step 2: Validate the new media paths

Replace `scene.clip_paths` usage with:

```python
for raw_path in [
    *(clip.file_path for clip in scene.clips),
    scene.narration_path,
]:
```

### Step 3: Trim clips and calculate the target

At the start of `_render_scene`:

```python
narration_duration = self._probe_duration(Path(scene.narration_path))
target_duration = max(scene.planned_duration, narration_duration)
```

Create inputs from `scene.clips`, set `audio_index = len(scene.clips)`, and build each video filter as:

```python
video_filter = (
    f"trim=duration={clip.planned_duration:.6f},"
    "setpts=PTS-STARTPTS,"
    "scale=1280:720:force_original_aspect_ratio=decrease,"
    "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
)
```

After single-clip selection or multi-clip concat, retain `tpad=stop_mode=clone:stop_duration=3600[scene_v]` so long narration holds the last frame.

Normalize and pad audio:

```python
filters.append(
    f"[{audio_index}:a:0]aresample=48000,"
    "aformat=sample_fmts=fltp:channel_layouts=stereo,"
    "asetpts=PTS-STARTPTS,"
    f"apad=whole_dur={target_duration:.6f}[scene_a]"
)
```

Set `-t` to `target_duration`.

### Step 4: Add a real local FFmpeg regression

Replace the old narration-led assertion with a test that creates:

- a 5.0s synthetic blue MP4;
- a 1.0s synthetic tone;
- `ClipMedia(planned_duration=2.0)`;
- `SceneMedia(planned_duration=2.0)`.

Probe the result duration with `imageio_ffmpeg.read_frames`, then inspect FFmpeg's
stream metadata and assert:

```python
assert 1.90 <= metadata["duration"] <= 2.15
probe = subprocess.run(
    [executable, "-hide_banner", "-i", str(output)],
    capture_output=True,
    text=True,
    check=False,
)
assert "Audio:" in probe.stderr
```

Keep the multi-scene real-FFmpeg test, updated to the new models.

### Step 5: Run focused tests

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_tools/test_ffmpeg.py -q
```

Expected: PASS, including the real local media tests.

### Step 6: Commit Task 7

```powershell
git add tools/ffmpeg.py tests/test_tools/test_ffmpeg.py
git commit -m "fix: assemble scenes to storyboard timing"
```

## Task 8: Update the quota-free seven-agent acceptance test

**Files:**

- Modify: `tests/test_e2e/test_end_to_end.py`

### Step 1: Make the synthetic services observable

Give `LocalVideoService` a `calls` list and generate a 5.2s color clip. Make `LocalTTSService` generate a 1.0s tone.

### Step 2: Update the mocked LLM sequence

Use only three LLM responses because Research now skips its call:

```python
llm.generate.side_effect = [
    '{"title":"Voxel","prompt":"Exactly one five-second scene and one shot",'
    '"tone":"playful","audience":"general","duration_seconds":5.0,'
    '"summary":"A voxel block reveal","requested_scene_count":1,'
    '"requested_shot_count":1,"requires_research":false}',
    '{"title":"Voxel","scenes":[{"scene_number":1,'
    '"narration":"A bright voxel block appears.","duration_hint":5.0,'
    '"visual_direction":"A cubic grass and soil block"}],'
    '"total_estimated_duration":5.0}',
    '{"shots":[{"shot_number":1,"scene_number":1,'
    '"visual_prompt":"A sharp cubic grass-and-soil block in a bright voxel world, '
    'flat pixel textures, clean square edges, no photorealistic foliage",'
    '"camera":"wide","motion":"slow orbit","duration":5.0}],'
    '"total_duration":5.0}',
]
```

### Step 3: Strengthen final assertions

Assert:

```python
assert llm.generate.call_count == 3
assert len(video_service.calls) == 1
storyboard = Storyboard.model_validate(
    result.agent_results[AgentName.STORYBOARD].output_data
)
assert len(storyboard.shots) == 1
reader = imageio_ffmpeg.read_frames(str(final_path))
metadata = next(reader)
reader.close()
assert 4.90 <= metadata["duration"] <= 5.15
probe = subprocess.run(
    [executable, "-hide_banner", "-i", str(final_path)],
    capture_output=True,
    text=True,
    check=False,
)
assert "Audio:" in probe.stderr
```

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_e2e/test_end_to_end.py -q
```

Expected: PASS with no external API usage.

### Step 4: Commit Task 8

```powershell
git add tests/test_e2e/test_end_to_end.py
git commit -m "test: lock one-shot five-second pipeline output"
```

## Task 9: Full verification and documentation alignment

**Files:**

- Modify only if needed: `PROJECT_SPEC.md` or the actual existing `PROJECT_SPEC*` file
- Modify only if needed: `README.md`

### Step 1: Run targeted Phase 4.1 tests

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agents/test_director.py tests/test_agents/test_research.py tests/test_agents/test_script.py tests/test_agents/test_storyboard.py tests/test_models/test_editor.py tests/test_agents/test_editor.py tests/test_tools/test_ffmpeg.py tests/test_e2e/test_end_to_end.py -q
```

Expected: PASS.

### Step 2: Run the full quota-free suite

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Expected: PASS with zero Alibaba/Wan/CosyVoice calls.

### Step 3: Check changed code for stale contracts

```powershell
rg "clip_paths|SceneMedia\(" agents models tools tests
rg "requested_scene_count|requested_shot_count|requires_research" agents models tests
git diff --check
git status --short
```

Expected:

- no runtime `clip_paths` references remain;
- the new brief fields appear in model, agents, and tests;
- `git diff --check` emits no errors;
- unrelated user files, including any manual-test symlink/link deletion, remain untouched.

### Step 4: Update project documentation only if it contradicts behavior

Document that automated tests are quota-free, explicit counts are enforced before Video, creative Research is skipped, and final timing follows `max(planned scene duration, narration duration)`. Do not rewrite unrelated phase history.

### Step 5: Final implementation commit

If documentation changed:

```powershell
git add PROJECT_SPEC.md README.md
git commit -m "docs: describe constraint-aware Phase 4 output"
```

If those exact files do not exist, stage only the actual documentation file discovered with `rg --files -g 'PROJECT_SPEC*' -g 'README*'`.

## Manual live smoke test (optional, one paid video call)

Do not run this during implementation. After all local tests pass, the user may manually submit:

```text
Create exactly one five-second scene with exactly one shot. Show a sharp cubic grass-and-soil block in a bright voxel game world, with flat pixel textures, clean square edges, and no photorealistic foliage. Use a slow camera orbit and brief narration.
```

Accept only when:

- Director records `requested_scene_count=1`, `requested_shot_count=1`, and `requires_research=false`;
- Research has zero notes and no fabricated sources;
- Video output contains exactly one clip, meaning one Wan call;
- final media duration is approximately five seconds;
- audio is present and the visual lasts after narration ends.
