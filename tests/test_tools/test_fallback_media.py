from pathlib import Path

import pytest

from tools import fallback_media


def test_placeholder_video_reports_ffmpeg_launch_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        fallback_media.imageio_ffmpeg,
        "get_ffmpeg_exe",
        lambda: "missing-ffmpeg",
    )

    with pytest.raises(fallback_media.FallbackMediaError, match="launch FFmpeg"):
        fallback_media.create_placeholder_video(
            str(tmp_path / "placeholder.mp4"),
            0.2,
        )

    assert not Path(tmp_path / "placeholder.mp4").exists()
