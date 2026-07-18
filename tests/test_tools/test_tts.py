from unittest.mock import MagicMock, patch

import dashscope
import pytest

from backend.config import VoiceConfig
from tools.tts import DashScopeTTSService


def test_synthesize_configures_websocket_client_and_writes_audio(
    tmp_path, monkeypatch
):
    endpoint = (
        "wss://workspace.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/inference"
    )
    config = VoiceConfig(
        api_key="test-key",
        base_url=endpoint,
        model="cosyvoice-v3-plus",
        voice="longanhuan",
    )
    service = DashScopeTTSService(config)
    output_path = tmp_path / "scene_001.mp3"
    synthesizer = MagicMock()
    synthesizer.call.return_value = b"mp3-audio"
    monkeypatch.setattr(dashscope, "api_key", None)
    monkeypatch.setattr(dashscope, "base_websocket_api_url", "")

    with patch(
        "dashscope.audio.tts_v2.SpeechSynthesizer",
        return_value=synthesizer,
    ) as synthesizer_class:
        result = service.synthesize("Narration", str(output_path))

    assert dashscope.api_key == "test-key"
    assert dashscope.base_websocket_api_url == endpoint
    synthesizer_class.assert_called_once_with(
        model="cosyvoice-v3-plus",
        voice="longanhuan",
    )
    synthesizer.call.assert_called_once_with("Narration")
    assert output_path.read_bytes() == b"mp3-audio"
    assert result == str(output_path)


@pytest.mark.parametrize("audio_data", [b"", None])
def test_synthesize_rejects_invalid_audio(tmp_path, monkeypatch, audio_data):
    service = DashScopeTTSService(
        VoiceConfig(
            api_key="test-key",
            model="cosyvoice-v3-plus",
            voice="longanhuan",
        )
    )
    output_path = tmp_path / "scene_001.mp3"
    synthesizer = MagicMock()
    synthesizer.call.return_value = audio_data
    monkeypatch.setattr(dashscope, "api_key", None)

    with patch(
        "dashscope.audio.tts_v2.SpeechSynthesizer",
        return_value=synthesizer,
    ):
        with pytest.raises(RuntimeError, match="empty audio"):
            service.synthesize("Narration", str(output_path))

    assert not output_path.exists()


def test_synthesize_preserves_sdk_default_endpoint_when_base_url_missing(
    tmp_path, monkeypatch
):
    default_endpoint = "wss://dashscope.example/api-ws/v1/inference"
    service = DashScopeTTSService(VoiceConfig(api_key="test-key", base_url=""))
    synthesizer = MagicMock()
    synthesizer.call.return_value = b"mp3-audio"
    monkeypatch.setattr(dashscope, "api_key", None)
    monkeypatch.setattr(dashscope, "base_websocket_api_url", default_endpoint)

    with patch(
        "dashscope.audio.tts_v2.SpeechSynthesizer",
        return_value=synthesizer,
    ):
        service.synthesize("Narration", str(tmp_path / "scene_001.mp3"))

    assert dashscope.base_websocket_api_url == default_endpoint


def test_synthesize_requires_api_key(tmp_path):
    service = DashScopeTTSService(VoiceConfig(api_key=""))

    with pytest.raises(RuntimeError, match="VOICE_API_KEY"):
        service.synthesize("Narration", str(tmp_path / "scene_001.mp3"))
