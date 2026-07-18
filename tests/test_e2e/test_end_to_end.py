"""Quota-free full pipeline test using local synthetic media."""

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
from models.storyboard import Storyboard
from models.workflow_state import WorkflowState
from storage.local import LocalStorage
from tools.ffmpeg import LocalFFmpegService
from tools.llm import LLMService
from tools.tts import TTSService
from tools.video_gen import VideoGenService
from workflow.pipeline import Pipeline


class LocalVideoService(VideoGenService):
    """Generate a tiny color clip without network access."""

    def __init__(self, executable: str):
        self.executable = executable
        self.calls: list[tuple[str, str]] = []

    def generate(self, prompt: str, output_path: str) -> str:
        self.calls.append((prompt, output_path))
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                self.executable,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=1280x720:d=5.2",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return str(path)


class LocalTTSService(TTSService):
    """Generate a tiny tone track without network access."""

    def __init__(self, executable: str):
        self.executable = executable

    def synthesize(self, text: str, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                self.executable,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=1.0",
                "-q:a",
                "4",
                str(path),
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
        '{"title":"Voxel","prompt":"Exactly one five-second scene and one shot",'
        '"tone":"playful","audience":"general","duration_seconds":5.0,'
        '"summary":"A voxel block reveal","requested_scene_count":1,'
        '"requested_shot_count":1,"requires_research":false}',
        '{"title":"Voxel","scenes":[{"scene_number":1,'
        '"narration":"A bright voxel block appears.","duration_hint":5.0,'
        '"visual_direction":"A cubic grass and soil block"}],'
        '"total_estimated_duration":5.0}',
        '{"shots":[{"shot_number":1,"scene_number":1,'
        '"visual_prompt":"A sharp cubic grass-and-soil block in a bright voxel '
        'world, flat pixel textures, clean square edges, no photorealistic foliage",'
        '"camera":"wide","motion":"slow orbit","duration":5.0}],'
        '"total_duration":5.0}',
    ]
    video_service = LocalVideoService(executable)
    agents = [
        DirectorAgent(llm_service=llm, storage=storage),
        ResearchAgent(llm_service=llm, storage=storage),
        ScriptAgent(llm_service=llm, storage=storage),
        StoryboardAgent(llm_service=llm, storage=storage),
        VideoAgent(
            video_service=video_service,
            storage=storage,
        ),
        VoiceAgent(
            tts_service=LocalTTSService(executable),
            storage=storage,
        ),
        EditorAgent(
            ffmpeg_service=LocalFFmpegService(executable),
            storage=storage,
            output_dir=output_root,
        ),
    ]
    state = WorkflowState(
        job_id="e2e-job",
        prompt="Exactly one five-second scene and one shot",
    )

    result = Pipeline(storage).run("e2e-job", agents, state)

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
    editor = EditorOutput.model_validate(
        result.agent_results[AgentName.EDITOR].output_data
    )
    final_path = Path(editor.final_path)
    assert final_path.is_file()
    assert final_path.stat().st_size > 1_000
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


def test_storyboard_constraint_failure_stops_before_video(tmp_path):
    storage = LocalStorage(str(tmp_path / "outputs"))
    llm = MagicMock(spec=LLMService)
    two_shots = (
        '{"shots":['
        '{"shot_number":1,"scene_number":1,"visual_prompt":"A",'
        '"camera":"wide","motion":"static","duration":2.5},'
        '{"shot_number":2,"scene_number":1,"visual_prompt":"B",'
        '"camera":"wide","motion":"static","duration":2.5}]}'
    )
    llm.generate.side_effect = [
        '{"title":"T","prompt":"one scene, one shot","tone":"clear",'
        '"audience":"general","duration_seconds":5,"summary":"S",'
        '"requested_scene_count":1,"requested_shot_count":1,'
        '"requires_research":false}',
        '{"title":"T","scenes":[{"scene_number":1,"narration":"N",'
        '"duration_hint":5,"visual_direction":"V"}]}',
        two_shots,
        two_shots,
    ]
    video_service = MagicMock(spec=VideoGenService)
    agents = [
        DirectorAgent(llm),
        ResearchAgent(llm),
        ScriptAgent(llm),
        StoryboardAgent(llm),
        VideoAgent(video_service),
    ]
    state = WorkflowState(job_id="blocked-job", prompt="one scene, one shot")

    result = Pipeline(storage).run("blocked-job", agents, state)

    assert result.status == JobStatus.FAILED
    assert result.failed_agent == AgentName.STORYBOARD
    video_service.generate.assert_not_called()
    assert AgentName.VIDEO not in result.agent_results
