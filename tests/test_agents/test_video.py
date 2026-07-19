from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.video import VideoAgent
from models.enums import AgentName
from models.workflow_state import WorkflowState
from models.agent_result import AgentResult
from models.storyboard import Shot, Storyboard
from models.video import VideoOutput
from storage.local import LocalStorage
from tools.video_gen import VideoGenService


def _make_context_with_storyboard(shot_count: int = 1) -> WorkflowState:
    ctx = WorkflowState(job_id="test-job", prompt="test")
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
    ctx.agent_results[AgentName.STORYBOARD] = AgentResult(
        agent_name=AgentName.STORYBOARD,
        success=True,
        output_data=storyboard.model_dump(mode="json"),
    )
    return ctx


def _mock_video_service() -> MagicMock:
    mock = MagicMock(spec=VideoGenService)

    def generate(prompt: str, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"video")
        return str(path)

    mock.generate.side_effect = generate
    return mock


class TestVideoAgent:
    def test_name_is_video(self):
        agent = VideoAgent(video_service=_mock_video_service())
        assert agent.name == AgentName.VIDEO

    def test_run_returns_workflow_state(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent = VideoAgent(video_service=_mock_video_service())
        ctx = _make_context_with_storyboard()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_run_raises_when_storyboard_missing(self):
        agent = VideoAgent(video_service=_mock_video_service())
        ctx = WorkflowState(job_id="test-job", prompt="test")
        with pytest.raises(ValueError, match="Storyboard"):
            agent.run(ctx)

    def test_run_generates_clip_for_each_shot(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_service = _mock_video_service()
        agent = VideoAgent(video_service=mock_service)
        ctx = _make_context_with_storyboard()
        result = agent.run(ctx)

        output_data = result.agent_results[AgentName.VIDEO].output_data
        video_output = VideoOutput.model_validate(output_data)
        assert len(video_output.clips) == 1
        assert video_output.clips[0].shot_number == 1
        assert Path(video_output.clips[0].file_path).parts[-3:] == ("video", "clips", "shot_001.mp4")
        mock_service.generate.assert_called_once()

    def test_run_persists_artifacts_to_storage(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_service = _mock_video_service()
        mock_storage = MagicMock()
        mock_storage.load.return_value = None
        agent = VideoAgent(video_service=mock_service, storage=mock_storage)
        ctx = _make_context_with_storyboard()
        agent.run(ctx)

        artifacts = ctx.agent_results[AgentName.VIDEO].artifacts
        assert len(artifacts) == 1
        assert artifacts[0].agent_name == AgentName.VIDEO
        assert artifacts[0].filename == "clips/shot_001.mp4"
        assert artifacts[0].content_type == "video/mp4"

    def test_run_raises_when_api_unavailable_and_fallback_disabled(self):
        mock_service = _mock_video_service()
        mock_service.generate.side_effect = RuntimeError("VIDEO_API_KEY not configured")
        agent = VideoAgent(video_service=mock_service, fallback_enabled=False)
        ctx = _make_context_with_storyboard()

        with pytest.raises(RuntimeError, match="VIDEO_API_KEY not configured"):
            agent.run(ctx)

    def test_run_persists_each_clip_and_resume_generates_only_missing(
        self,
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

    @pytest.mark.parametrize("damage", ["missing", "empty"])
    def test_run_regenerates_invalid_manifest_file(
        self,
        tmp_path,
        monkeypatch,
        damage,
    ):
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
