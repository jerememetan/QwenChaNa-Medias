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

    def generate(self, prompt: str, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                self.executable,
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=1280x720:d=0.4",
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
                "sine=frequency=440:duration=0.6",
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
        '{"title":"AI","prompt":"Explain AI briefly","tone":"clear",'
        '"audience":"general","duration_seconds":1.0,"summary":"AI summary"}',
        '{"brief_summary":"AI summary","notes":[],"overall_confidence":0.8}',
        '{"title":"AI","scenes":[{"scene_number":1,'
        '"narration":"AI helps people solve problems.","duration_hint":0.6,'
        '"visual_direction":"Blue technology background"}]}',
        '{"shots":[{"shot_number":1,"scene_number":1,'
        '"visual_prompt":"Blue technology background","camera":"wide",'
        '"motion":"static","duration":0.4}]}',
    ]
    agents = [
        DirectorAgent(llm_service=llm, storage=storage),
        ResearchAgent(llm_service=llm, storage=storage),
        ScriptAgent(llm_service=llm, storage=storage),
        StoryboardAgent(llm_service=llm, storage=storage),
        VideoAgent(
            video_service=LocalVideoService(executable),
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
    state = WorkflowState(job_id="e2e-job", prompt="Explain AI briefly")

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
