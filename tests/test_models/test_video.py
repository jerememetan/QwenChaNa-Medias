from pydantic import ValidationError
import pytest

from models.video import VideoClip, VideoOutput


class TestVideoClip:
    def test_valid_clip(self):
        clip = VideoClip(shot_number=1, file_path="video/clips/shot_001.mp4")
        assert clip.shot_number == 1
        assert clip.file_path == "video/clips/shot_001.mp4"
        assert clip.duration is None

    def test_invalid_shot_number(self):
        with pytest.raises(ValidationError):
            VideoClip(shot_number=0, file_path="video/clips/shot_001.mp4")


class TestVideoOutput:
    def test_valid_output(self):
        output = VideoOutput(
            clips=[
                VideoClip(shot_number=1, file_path="video/clips/shot_001.mp4"),
                VideoClip(shot_number=2, file_path="video/clips/shot_002.mp4"),
            ]
        )
        assert len(output.clips) == 2