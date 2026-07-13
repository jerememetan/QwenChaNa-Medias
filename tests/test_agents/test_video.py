from unittest.mock import MagicMock

import pytest

from agents.video import VideoAgent
from models.enums import AgentName
from models.workflow_state import WorkflowState
from models.agent_result import AgentResult
from models.storyboard import Shot, Storyboard
from models.video import VideoOutput
from tools.video_gen import VideoGenService


def _make_context_with_storyboard() -> WorkflowState:
    ctx = WorkflowState(job_id="test-job", prompt="test")
    storyboard = Storyboard(
        shots=[
            Shot(
                shot_number=1,
                scene_number=1,
                visual_prompt="A calm forest",
                camera="wide",
                motion="static",
                duration=5.0,
            )
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
    mock.generate.side_effect = lambda prompt, output_path: output_path
    return mock


class TestVideoAgent:
    def test_name_is_video(self):
        agent = VideoAgent(video_service=_mock_video_service())
        assert agent.name == AgentName.VIDEO

    def test_run_returns_workflow_state(self):
        agent = VideoAgent(video_service=_mock_video_service())
        ctx = _make_context_with_storyboard()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_run_raises_when_storyboard_missing(self):
        agent = VideoAgent(video_service=_mock_video_service())
        ctx = WorkflowState(job_id="test-job", prompt="test")
        with pytest.raises(ValueError, match="Storyboard"):
            agent.run(ctx)

    def test_run_generates_clip_for_each_shot(self):
        mock_service = _mock_video_service()
        agent = VideoAgent(video_service=mock_service)
        ctx = _make_context_with_storyboard()
        result = agent.run(ctx)

        output_data = result.agent_results[AgentName.VIDEO].output_data
        video_output = VideoOutput.model_validate(output_data)
        assert len(video_output.clips) == 1
        assert video_output.clips[0].shot_number == 1
        from pathlib import PurePath
        assert PurePath(video_output.clips[0].file_path).parts[-3:] == ("video", "clips", "shot_001.mp4")
        mock_service.generate.assert_called_once()

    def test_run_persists_artifacts_to_storage(self):
        mock_service = _mock_video_service()
        mock_storage = MagicMock()
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
