from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agents.voice import VoiceAgent
from models.enums import AgentName
from models.workflow_state import WorkflowState
from models.agent_result import AgentResult
from models.script import Script
from models.scene import Scene
from models.voice import VoiceOutput
from storage.local import LocalStorage
from tools.tts import TTSService


def _make_context_with_script(scene_count: int = 1) -> WorkflowState:
    ctx = WorkflowState(job_id="test-job", prompt="test")
    script = Script(
        title="AI Explainer",
        scenes=[
            Scene(
                scene_number=number,
                narration=f"Narration {number}",
                duration_hint=5.0,
                visual_direction=f"Visual {number}",
            )
            for number in range(1, scene_count + 1)
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

    def synthesize(text: str, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"audio")
        return str(path)

    mock.synthesize.side_effect = synthesize
    return mock


class TestVoiceAgent:
    def test_name_is_voice(self):
        agent = VoiceAgent(tts_service=_mock_tts_service())
        assert agent.name == AgentName.VOICE

    def test_run_returns_workflow_state(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        agent = VoiceAgent(tts_service=_mock_tts_service())
        ctx = _make_context_with_script()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_run_raises_when_script_missing(self):
        agent = VoiceAgent(tts_service=_mock_tts_service())
        ctx = WorkflowState(job_id="test-job", prompt="test")
        with pytest.raises(ValueError, match="Script"):
            agent.run(ctx)

    def test_run_generates_track_for_each_scene(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_service = _mock_tts_service()
        agent = VoiceAgent(tts_service=mock_service)
        ctx = _make_context_with_script()
        result = agent.run(ctx)

        output_data = result.agent_results[AgentName.VOICE].output_data
        voice_output = VoiceOutput.model_validate(output_data)
        assert len(voice_output.tracks) == 1
        assert voice_output.tracks[0].scene_number == 1
        assert Path(voice_output.tracks[0].file_path).parts[-3:] == (
            "voice", "audio", "scene_001.mp3"
        )
        mock_service.synthesize.assert_called_once()

    def test_run_uses_configured_output_directory(self, tmp_path):
        output_dir = tmp_path / "custom-media"
        service = _mock_tts_service()

        VoiceAgent(service, output_dir=output_dir).run(
            _make_context_with_script()
        )

        generated_path = Path(service.synthesize.call_args.args[1])
        assert generated_path == (
            output_dir / "test-job" / "voice" / "audio" / "scene_001.mp3"
        )

    def test_run_persists_artifacts_to_storage(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mock_service = _mock_tts_service()
        mock_storage = MagicMock()
        mock_storage.load.return_value = None
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

    def test_run_generates_placeholder_when_fallback_enabled(
        self,
        tmp_path,
    ):
        service = _mock_tts_service()
        service.synthesize.side_effect = RuntimeError("quota exhausted")
        context = _make_context_with_script()
        context.agent_results[AgentName.SCRIPT].output_data["scenes"][0][
            "duration_hint"
        ] = 0.2

        result = VoiceAgent(
            service,
            fallback_enabled=True,
            output_dir=tmp_path,
        ).run(context)

        track = VoiceOutput.model_validate(
            result.agent_results[AgentName.VOICE].output_data
        ).tracks[0]
        assert Path(track.file_path).is_file()
        assert Path(track.file_path).stat().st_size > 0

    def test_run_persists_each_track_and_resume_generates_only_missing(
        self,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.chdir(tmp_path)
        storage = LocalStorage("outputs")
        context = _make_context_with_script(scene_count=2)
        first_service = _mock_tts_service()

        def fail_second(text: str, output_path: str) -> str:
            if output_path.endswith("scene_002.mp3"):
                raise RuntimeError("voice quota exhausted")
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"first")
            return str(path)

        first_service.synthesize.side_effect = fail_second

        with pytest.raises(RuntimeError, match="voice quota exhausted"):
            VoiceAgent(first_service, storage=storage).run(context)

        partial = VoiceOutput.model_validate(
            storage.load("test-job", "voice", "voice_output.json")
        )
        assert [track.scene_number for track in partial.tracks] == [1]

        resumed_service = _mock_tts_service()
        result = VoiceAgent(resumed_service, storage=storage).run(context)

        resumed_service.synthesize.assert_called_once()
        assert resumed_service.synthesize.call_args.args[1].endswith(
            "scene_002.mp3"
        )
        output = VoiceOutput.model_validate(
            result.agent_results[AgentName.VOICE].output_data
        )
        assert [track.scene_number for track in output.tracks] == [1, 2]

    @pytest.mark.parametrize("damage", ["missing", "empty"])
    def test_run_regenerates_invalid_manifest_file(
        self,
        tmp_path,
        monkeypatch,
        damage,
    ):
        monkeypatch.chdir(tmp_path)
        storage = LocalStorage("outputs")
        context = _make_context_with_script()
        VoiceAgent(_mock_tts_service(), storage=storage).run(context)
        path = Path("outputs/test-job/voice/audio/scene_001.mp3")
        if damage == "missing":
            path.unlink()
        else:
            path.write_bytes(b"")
        del context.agent_results[AgentName.VOICE]
        service = _mock_tts_service()

        VoiceAgent(service, storage=storage).run(context)

        service.synthesize.assert_called_once()
        assert path.stat().st_size > 0
