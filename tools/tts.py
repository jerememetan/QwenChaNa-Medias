"""TTS service abstraction — agents call this interface, never raw APIs."""

from abc import ABC, abstractmethod
from pathlib import Path

import dashscope

from backend.config import VoiceConfig


class TTSService(ABC):
    """Abstract interface for text-to-speech generation."""

    @abstractmethod
    def synthesize(self, text: str, output_path: str) -> str:
        """Synthesize speech from text and save to file.

        Args:
            text: The text to convert to speech.
            output_path: Path to save the audio file.

        Returns:
            The path to the generated audio file.
        """
        ...


class DashScopeTTSService(TTSService):
    """Concrete TTS service using Alibaba Cloud Model Studio CosyVoice.

    Uses the ``dashscope`` Python SDK's SpeechSynthesizer for
    text-to-speech generation via the CosyVoice model.
    """

    def __init__(self, config: VoiceConfig) -> None:
        self.config = config
        self._configured = bool(config.api_key)
        if config.api_key:
            dashscope.api_key = config.api_key

    def synthesize(self, text: str, output_path: str) -> str:
        if not self._configured:
            raise RuntimeError(
                "DashScopeTTSService has no API key configured — "
                "set VOICE_API_KEY in .env or pass api_key to VoiceConfig"
            )

        from dashscope.audio.tts_v2 import SpeechSynthesizer

        synthesizer = SpeechSynthesizer(
            model=self.config.model,
            voice=self.config.voice,
        )
        audio_data = synthesizer.call(text)

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(audio_data)
        return str(path)
