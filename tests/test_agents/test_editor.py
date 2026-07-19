"""Editor Agent tests."""

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
    storyboard = Storyboard(
        shots=[
            Shot(
                shot_number=1,
                scene_number=1,
                visual_prompt="a",
                camera="wide",
                motion="pan",
                duration=5,
            ),
            Shot(
                shot_number=2,
                scene_number=1,
                visual_prompt="b",
                camera="wide",
                motion="pan",
                duration=5,
            ),
            Shot(
                shot_number=3,
                scene_number=2,
                visual_prompt="c",
                camera="wide",
                motion="pan",
                duration=5,
            ),
        ]
    )
    video = VideoOutput(
        clips=[
            VideoClip(shot_number=i, file_path=clip_paths[i - 1], duration=5)
            for i in (1, 2, 3)
        ]
    )
    voice = VoiceOutput(
        tracks=[
            AudioTrack(scene_number=i, file_path=track_paths[i - 1], duration=5)
            for i in (1, 2)
        ]
    )
    for name, value in (
        (AgentName.STORYBOARD, storyboard),
        (AgentName.VIDEO, video),
        (AgentName.VOICE, voice),
    ):
        state.agent_results[name] = AgentResult(
            agent_name=name,
            success=True,
            output_data=value.model_dump(mode="json"),
        )
    return state


def _service() -> MagicMock:
    service = MagicMock(spec=FFmpegService)

    def assemble(scenes, output_path):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"final")
        return output_path

    service.assemble.side_effect = assemble
    return service


def test_editor_groups_clips_by_scene_in_storyboard_order(tmp_path):
    service = _service()
    agent = EditorAgent(service, output_dir=tmp_path / "outputs")

    agent.run(_context(tmp_path))

    scenes = service.assemble.call_args.args[0]
    assert [scene.scene_number for scene in scenes] == [1, 2]
    assert [clip.shot_number for clip in scenes[0].clips] == [1, 2]
    assert [clip.planned_duration for clip in scenes[0].clips] == [5.0, 5.0]
    assert len(scenes[1].clips) == 1
    assert scenes[0].planned_duration == 10.0
    assert scenes[1].planned_duration == 5.0


def test_editor_writes_result_metadata_and_artifact(tmp_path):
    storage = LocalStorage(str(tmp_path / "outputs"))
    state = _context(tmp_path)
    result = EditorAgent(
        _service(),
        storage=storage,
        output_dir=tmp_path / "outputs",
    ).run(state)

    output = EditorOutput.model_validate(
        result.agent_results[AgentName.EDITOR].output_data
    )
    assert Path(output.final_path).read_bytes() == b"final"
    assert output.scene_count == 2
    artifact = result.agent_results[AgentName.EDITOR].artifacts[0]
    assert artifact.filename == "final/final_video.mp4"
    assert artifact.size_bytes == 5
    assert storage.exists("editor-job", "editor", "editor_output.json")


@pytest.mark.parametrize(
    "missing",
    [AgentName.STORYBOARD, AgentName.VIDEO, AgentName.VOICE],
)
def test_editor_rejects_missing_upstream_result(tmp_path, missing):
    state = _context(tmp_path)
    del state.agent_results[missing]

    with pytest.raises(ValueError, match=missing.value):
        EditorAgent(_service(), output_dir=tmp_path).run(state)


@pytest.mark.parametrize(
    "failed",
    [AgentName.STORYBOARD, AgentName.VIDEO, AgentName.VOICE],
)
def test_editor_rejects_failed_upstream_result(tmp_path, failed):
    state = _context(tmp_path)
    state.agent_results[failed].success = False

    with pytest.raises(ValueError, match=rf"{failed.value} failed"):
        EditorAgent(_service(), output_dir=tmp_path).run(state)


def test_editor_rejects_missing_shot_clip(tmp_path):
    state = _context(tmp_path)
    state.agent_results[AgentName.VIDEO].output_data["clips"].pop()

    with pytest.raises(ValueError, match="shot 3"):
        EditorAgent(_service(), output_dir=tmp_path).run(state)


def test_editor_rejects_missing_scene_narration(tmp_path):
    state = _context(tmp_path)
    state.agent_results[AgentName.VOICE].output_data["tracks"].pop()

    with pytest.raises(ValueError, match="scene 2"):
        EditorAgent(_service(), output_dir=tmp_path).run(state)


def test_editor_rejects_duplicate_video_clip_identifier(tmp_path):
    state = _context(tmp_path)
    clips = state.agent_results[AgentName.VIDEO].output_data["clips"]
    clips[1]["shot_number"] = clips[0]["shot_number"]

    with pytest.raises(ValueError, match="duplicate video clip"):
        EditorAgent(_service(), output_dir=tmp_path).run(state)


def test_editor_rejects_duplicate_narration_identifier(tmp_path):
    state = _context(tmp_path)
    tracks = state.agent_results[AgentName.VOICE].output_data["tracks"]
    tracks[1]["scene_number"] = tracks[0]["scene_number"]

    with pytest.raises(ValueError, match="duplicate narration"):
        EditorAgent(_service(), output_dir=tmp_path).run(state)


def test_editor_rejects_missing_media_file(tmp_path):
    state = _context(tmp_path)
    missing_path = state.agent_results[AgentName.VIDEO].output_data["clips"][0][
        "file_path"
    ]
    Path(missing_path).unlink()

    with pytest.raises(FileNotFoundError, match="does not exist"):
        EditorAgent(_service(), output_dir=tmp_path).run(state)
