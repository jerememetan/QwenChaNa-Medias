from pathlib import PurePath
from unittest.mock import MagicMock

import pytest

from agents.voice import VoiceAgent
from models.enums import AgentName
from models.workflow_state import WorkflowState
from models.agent_result import AgentResult
from models.script import Script
from models.scene import Scene
from models.voice import VoiceOutput
from tools.tts import TTSService


def _make_context_with_script() -> WorkflowState:
    ctx = WorkflowState(job_id="test-job", prompt="test")
    script = Script(
        title="AI Explainer",
        scenes=[
            Scene(
                scene_number=1,
                narration="AI is transforming the world.",
                duration_hint=5.0,
                visual_direction="Show AI systems",
            )
        ],
    )
    ctx.agent_results[AgentName.SCRIPT] = AgentResult(
        agent_name=AgentName.SCRIPT,
        success=True,
        output_data=script.model_dump(mode="json"),
    )
    return ctx


def _mock_tts_service() -> MagicMock:
    mock = MagicMock(spec=TTSService)
    mock.synthesize.side_effect = lambda text, output_path: output_path
    return mock


class TestVoiceAgent:
    def test_name_is_voice(self):
        agent = VoiceAgent(tts_service=_mock_tts_service())
        assert agent.name == AgentName.VOICE

    def test_run_returns_workflow_state(self):
        agent = VoiceAgent(tts_service=_mock_tts_service())
        ctx = _make_context_with_script()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_run_raises_when_script_missing(self):
        agent = VoiceAgent(tts_service=_mock_tts_service())
        ctx = WorkflowState(job_id="test-job", prompt="test")
        with pytest.raises(ValueError, match="Script"):
            agent.run(ctx)

    def test_run_generates_track_for_each_scene(self):
        mock_service = _mock_tts_service()
        agent = VoiceAgent(tts_service=mock_service)
        ctx = _make_context_with_script()
        result = agent.run(ctx)

        output_data = result.agent_results[AgentName.VOICE].output_data
        voice_output = VoiceOutput.model_validate(output_data)
        assert len(voice_output.tracks) == 1
        assert voice_output.tracks[0].scene_number == 1
        assert PurePath(voice_output.tracks[0].file_path).parts[-3:] == (
            "voice", "audio", "scene_001.mp3"
        )
        mock_service.synthesize.assert_called_once()

    def test_run_persists_artifacts_to_storage(self):
        mock_service = _mock_tts_service()
        mock_storage = MagicMock()
        agent = VoiceAgent(tts_service=mock_service, storage=mock_storage)
        ctx = _make_context_with_script()
        agent.run(ctx)

        artifacts = ctx.agent_results[AgentName.VOICE].artifacts
        assert len(artifacts) == 1
        assert artifacts[0].agent_name == AgentName.VOICE
        assert artifacts[0].filename == "audio/scene_001.mp3"
        assert artifacts[0].content_type == "audio/mpeg"

    def test_run_raises_when_api_unavailable_and_fallback_disabled(self):
        mock_service = _mock_tts_service()
        mock_service.synthesize.side_effect = RuntimeError("VOICE_API_KEY not configured")
        agent = VoiceAgent(tts_service=mock_service, fallback_enabled=False)
        ctx = _make_context_with_script()

        with pytest.raises(RuntimeError, match="VOICE_API_KEY not configured"):
            agent.run(ctx)
