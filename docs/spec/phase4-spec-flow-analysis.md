# Phase 4 — Spec Flow Analysis: Assembly

> **Scope:** Editor Agent, FFmpeg-based assembly, quota-free prompt-to-MP4 testing, resume from Editor failure, job status, and final-video retrieval.
> **Grounded in:** The Phase 1–3 pipeline, API, storage, media output models, and tests as they exist on 2026-07-19.

---

## 1. Codebase Context

| Component | Current state | Phase 4 consequence |
| --- | --- | --- |
| `VideoOutput` | Lists clips by `shot_number`, path, and expected duration | Editor must join clips to storyboard shots to recover scene membership. |
| `VoiceOutput` | Lists narration tracks by `scene_number`, path, and expected duration | Editor can pair one narration track with each storyboard scene. |
| `Storyboard` | Supports multiple ordered shots per scene | Assembly cannot assume one clip per narration track. |
| `agents/editor.py` | Empty | Editor contract and validation remain to be implemented. |
| `tools/ffmpeg.py` | Empty | FFmpeg invocation, binary discovery, and error translation remain to be implemented. |
| `backend/main.py` | Wires six agents, ending with Voice | A job can currently complete without producing a final MP4. |
| `GET /result/{job_id}` | Returns the job directory and artifact metadata | It does not identify or download the final MP4. |
| `POST /resume/{job_id}` | Returns `202` without calling `resume_job` | The route acknowledges a resume but does not resume processing. |
| Pipeline failure handling | Persists `failed_agent`, `error`, and completed upstream results | The base behavior needed to retry only Editor already exists. |
| FFmpeg runtime | `ffmpeg` and `ffprobe` are not on PATH on the current Windows machine | `ffmpeg-python` alone is insufficient; Phase 4 must provide or resolve an executable. |

Existing conventions to preserve:

- Agents validate typed upstream outputs, call an injected service, persist JSON metadata, then add an `AgentResult`.
- Binary artifacts are written directly to disk; `StorageBackend` persists JSON only.
- The pipeline remains synchronous and sequential until Phase 5.
- Media tests must not invoke Alibaba APIs or consume paid quota.

---

## 2. User Flows

### Flow 1: Generate and assemble a final video

1. The user sends `POST /generate` with a prompt.
2. Director through Voice complete sequentially.
3. Editor reads Storyboard, Video, and Voice results.
4. Editor groups storyboard shots by scene while preserving storyboard order.
5. For each scene, FFmpeg concatenates its clips, removes source audio, normalizes to 1280×720 at 30 fps, and overlays that scene's narration.
6. Narration controls scene length: video is trimmed when longer than narration and its final frame is held when narration is longer.
7. FFmpeg concatenates the scene segments with hard cuts.
8. Editor writes `outputs/{job_id}/editor/final/final_video.mp4`, persists `editor_output.json`, and records an MP4 artifact.
9. Pipeline marks the job completed.

Terminal states:

- **Completed:** a non-empty final MP4 exists and Editor has a successful result.
- **Failed at Editor:** upstream results remain persisted; no successful Editor result is written.

### Flow 2: Assembly input is incomplete or invalid

1. Editor validates the three required upstream results.
2. It checks for duplicate shot/scene identifiers, missing shot clips, missing narration tracks, empty scene groups, and nonexistent files.
3. A validation failure raises a specific error before FFmpeg runs.
4. Pipeline records `status=failed`, `failed_agent=editor`, and the error message.

### Flow 3: FFmpeg fails and the user resumes

1. FFmpeg exits non-zero or cannot be launched.
2. The FFmpeg wrapper raises an error containing a short stderr summary.
3. Pipeline persists the failed Editor state while retaining Director through Voice results.
4. The user calls `POST /resume/{job_id}` after correcting the runtime or media problem.
5. `resume_job` skips every successful upstream agent and runs Editor again.
6. The API updates the `JobRecord` to completed or failed based on the resumed pipeline result.

### Flow 4: Retrieve the final output

1. Before completion, `GET /result/{job_id}` and the download route return `409`.
2. After completion, `GET /result/{job_id}` returns the exact final-video path, its artifact metadata, and a download URL.
3. `GET /result/{job_id}/download` returns the MP4 as `video/mp4` with a download filename.
4. If context says completed but the final file is missing, the download route returns `404` rather than an empty response.

---

## 3. Gaps

### Critical

**G1: No FFmpeg executable is available.** The installed Python wrapper does not include an executable, and both `ffmpeg` and `ffprobe` are absent from PATH. Implementation and integration tests would fail immediately.

**Resolution:** depend on `imageio-ffmpeg` for a cross-platform bundled executable, while allowing an explicit binary path override for deployment.

**G2: Scene synchronization policy is unspecified.** Generated video and synthesized narration can have different real durations. Using a global `-shortest` could truncate narration or drift scene boundaries.

**Resolution:** assemble one scene at a time. Narration is authoritative; hold the final video frame when visuals are short and trim visuals when they are long. Then concatenate complete scene segments.

**G3: Shot-to-scene mapping is indirect.** `VideoClip` lacks `scene_number`, and multiple shots may belong to one scene.

**Resolution:** use `Storyboard.shots` as the canonical order and mapping. Validate that every storyboard shot has exactly one clip and every referenced scene has exactly one narration track.

**G4: Production never runs Editor.** `backend/main.py` stops after Voice, so the pipeline may report completion without a final MP4.

**Resolution:** construct the FFmpeg service and append `EditorAgent` as the seventh production agent.

**G5: Resume and result API behavior do not meet the Phase 4/MVP flow.** Resume is currently a no-op, and result identifies only a directory.

**Resolution:** execute `resume_job` inside the resume route, synchronize `JobRecord`, return the exact Editor output in result metadata, and add a file download route.

### Important

**G6: Invalid media should fail before launching FFmpeg.** Missing files otherwise produce provider-specific stderr that is hard to diagnose.

**Resolution:** Editor validates required result schemas, identifier coverage, and local file existence first.

**G7: Temporary assembly files need deterministic cleanup.** Per-scene rendering creates intermediate MP4s that must not remain after success or failure.

**Resolution:** create them in a `TemporaryDirectory` under the Editor output directory and let the context manager clean them up.

**G8: Tests could accidentally spend quota.** A live full-pipeline test invokes LLM, video, and TTS providers.

**Resolution:** the automated end-to-end test uses fixed LLM responses plus local FFmpeg-generated color video and tone audio. A live smoke test remains manual and opt-in.

### Minor

**G9: Actual duration is not yet exposed in `EditorOutput`.** Accurate probing is useful but not required to return a valid file.

**Resolution:** store `final_path` and `scene_count` in the MVP. Duration metadata can be added after assembly is stable.

**G10: Source clips are already 1280×720, but codec details may vary.** Direct stream-copy concatenation could fail despite matching dimensions.

**Resolution:** re-encode scene segments and the final MP4 to H.264/AAC, `yuv420p`, 1280×720, and 30 fps for deterministic playback.

---

## 4. Resolved Questions

| Question | Resolution |
| --- | --- |
| What is the first Phase 4 visual scope? | Hard cuts only; no titles, transitions, background music, or effects. |
| What output geometry is required? | 1280×720 at 30 fps; incoming clips already use 1280×720 but are normalized during encoding. |
| What determines each scene's length? | Narration. Visuals are trimmed or their last frame is held to preserve all spoken audio. |
| How are multiple shots handled? | Concatenate all shots for a scene in storyboard order before narration is applied. |
| How is FFmpeg supplied on Windows? | `imageio-ffmpeg` bundled executable, with a constructor override for deployment. |
| How is final media returned? | Metadata from `/result/{job_id}` plus MP4 bytes from `/result/{job_id}/download`. |
| Can automated tests call paid APIs? | No. All Phase 4 automated media generation is local and deterministic. |

---

## 5. Recommended Implementation Order

1. Define `SceneMedia` and `EditorOutput` contracts.
2. Implement and test the subprocess-based FFmpeg service with bundled-binary discovery.
3. Implement Editor validation, scene grouping, persistence, and artifact recording.
4. Wire Editor into production and expose exact result/download behavior.
5. Make the resume route execute the existing resume workflow and synchronize status.
6. Add a quota-free seven-agent prompt-to-MP4 test and an Editor-specific resume test.
7. Run focused tests, then the full `tests/` suite; do not run `run_test.py` automatically.
