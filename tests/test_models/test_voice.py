from pydantic import ValidationError
import pytest

from models.voice import AudioTrack, VoiceOutput


class TestAudioTrack:
    def test_valid_track(self):
        track = AudioTrack(scene_number=1, file_path="voice/audio/scene_001.mp3")
        assert track.scene_number == 1
        assert track.file_path == "voice/audio/scene_001.mp3"
        assert track.duration is None

    def test_invalid_scene_number(self):
        with pytest.raises(ValidationError):
            AudioTrack(scene_number=0, file_path="voice/audio/scene_001.mp3")


class TestVoiceOutput:
    def test_valid_output(self):
        output = VoiceOutput(
            tracks=[
                AudioTrack(scene_number=1, file_path="voice/audio/scene_001.mp3"),
            ]
        )
        assert len(output.tracks) == 1