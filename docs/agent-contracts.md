# Agent Contracts

All pipeline agents expose `name: AgentName` and
`run(context: WorkflowState) -> WorkflowState`. Successful agents add an
`AgentResult` and persist their metadata before returning. Exceptions are
captured by `Pipeline`, which records the failed agent and error.

## Editor Agent

**Required context results:**

- `Storyboard`: canonical shot order and shot-to-scene mapping.
- `VideoOutput`: generated clip path for each `shot_number`.
- `VoiceOutput`: narration path for each `scene_number`.

Editor groups clips by scene in storyboard order and passes these values to
the FFmpeg service:

```python
class SceneMedia(BaseModel):
    scene_number: int
    clip_paths: list[str]
    narration_path: str
```

It writes this result to `agent_results[AgentName.EDITOR]` and
`editor/editor_output.json`:

```python
class EditorOutput(BaseModel):
    final_path: str
    scene_count: int
```

The final artifact is `editor/final/final_video.mp4` with content type
`video/mp4`. Output uses hard cuts, H.264/AAC, 1280×720, and 30 fps. Narration
sets each scene's duration: longer visuals are trimmed and shorter visuals hold
their final frame.

Editor raises before FFmpeg when upstream results, clip mappings, narration
mappings, or input files are missing. FFmpeg launch and encoding failures raise
`FFmpegError`; pipeline persistence makes the job resumable from Editor.
