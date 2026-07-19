# Phase 4 Assembly Design

## Scope

Phase 4 completes the sequential MVP by turning Phase 3 video clips and narration tracks into one downloadable MP4. The first implementation uses hard cuts, narration-led scene timing, 1280×720 H.264 video, AAC audio, and no titles, transitions, music, or effects.

## Architecture

The change adds two focused units:

- `EditorAgent` owns pipeline concerns: reading typed upstream results, validating coverage and files, grouping shots into scenes, choosing the output path, persisting `EditorOutput`, and recording the final artifact.
- `FFmpegService` owns media concerns: locating an FFmpeg executable, rendering per-scene audio/video segments, concatenating those segments, and translating process failures into actionable Python errors.

`EditorAgent` depends on the service interface rather than subprocess directly. This follows the existing Video and Voice agent pattern and makes agent tests fast while keeping one real local-media integration test.

## Alternatives Considered

1. **Per-scene narrated assembly (selected):** render each scene against its own narration, then concatenate scenes. It handles multiple shots per scene and prevents timing drift, at the cost of temporary files and an additional encode.
2. **Globally concatenate video and audio separately:** this needs fewer FFmpeg operations, but any duration mismatch shifts every later scene and can truncate narration.
3. **Probe every file and construct one exact filter graph:** this can minimize intermediate files, but adds duration-probing and filter-graph complexity that does not improve the hackathon MVP enough to justify it.

## Data Contracts

`SceneMedia` is the boundary between Editor and FFmpeg:

```python
class SceneMedia(BaseModel):
    scene_number: int
    clip_paths: list[str]
    narration_path: str
```

`EditorOutput` is stored in the workflow context:

```python
class EditorOutput(BaseModel):
    final_path: str
    scene_count: int
```

Storyboard remains the source of truth for ordering and for mapping `shot_number` to `scene_number`. Video and Voice outputs supply the actual paths.

## Assembly Flow

For each scene in first-appearance storyboard order:

1. Normalize every clip to 1280×720, square pixels, 30 fps, and reset timestamps.
2. Concatenate all normalized visual clips for that scene.
3. Remove any source clip audio.
4. Reset and resample narration to stereo 48 kHz.
5. Extend the final visual frame, then use narration as the stopping condition. This preserves all narration and avoids cross-scene timing drift.
6. Encode an H.264/AAC temporary scene MP4.

After all scenes render, FFmpeg concatenates their video/audio streams in order and writes `outputs/{job_id}/editor/final/final_video.mp4`. Temporary files live under the final directory and are removed on both success and failure.

## Validation and Errors

Editor fails before FFmpeg when:

- Storyboard, Video, or Voice results are absent or invalid.
- A storyboard shot has no matching clip.
- A referenced scene has no matching narration track.
- Duplicate clip or narration identifiers make mapping ambiguous.
- A referenced input path does not exist or is not a file.

The FFmpeg service raises `FFmpegError` when the executable cannot be resolved, a command exits non-zero, or the expected output is absent/empty. Error text includes the operation name and a bounded stderr tail so the persisted job error is useful without becoming enormous.

## Runtime Distribution

The current Windows environment has no `ffmpeg` or `ffprobe` command. Phase 4 therefore uses `imageio-ffmpeg` to supply a cross-platform FFmpeg binary. The concrete service still accepts an explicit executable path so deployment images can use a system package.

## API Behavior

`GET /result/{job_id}` remains a JSON metadata endpoint for compatibility, but its `output_path` becomes the exact final MP4 and it exposes `download_url`. `GET /result/{job_id}/download` serves the file as `video/mp4`.

`POST /resume/{job_id}` invokes the existing `resume_job` function with the configured agents, then updates `JobRecord` from the returned `WorkflowState`. Since Phase 4 remains synchronous, the request finishes after the resumed work finishes even though the API retains its existing `202` response.

## Testing Strategy

- Model tests validate both new Pydantic contracts.
- FFmpeg unit tests mock process execution to check command construction and failure translation.
- One FFmpeg integration test uses the bundled executable to create tiny synthetic clips/audio and verifies a non-empty final MP4. It performs no network calls.
- Editor tests mock `FFmpegService` to cover mapping, persistence, missing inputs, duplicate identifiers, and missing files.
- The end-to-end test runs all seven agents using fixed LLM responses and local synthetic media services.
- Resume testing fails Editor once, persists upstream results, resumes with a successful Editor, and proves upstream agents were skipped.
- API tests cover the exact result path, download response, missing final file, and real resume execution.

`run_test.py` remains outside automated verification because it is a paid live smoke test.

## Deferred Work

Transitions, titles, background music, per-word synchronization, aspect-ratio variants, asynchronous generation, and parallel Video/Voice execution remain outside Phase 4 and belong in later milestones.
