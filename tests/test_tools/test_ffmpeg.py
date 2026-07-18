"""FFmpeg assembly service tests."""

from pathlib import Path
import subprocess

import imageio_ffmpeg
import pytest

from models.editor import SceneMedia
from tools.ffmpeg import FFmpegError, LocalFFmpegService


class RecordingFFmpegService(LocalFFmpegService):
    """Record commands and create fake outputs without launching FFmpeg."""

    def __init__(self):
        super().__init__(executable="ffmpeg-test")
        self.commands: list[list[str]] = []

    def _run(self, command: list[str], operation: str) -> None:
        self.commands.append(command)
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_bytes(b"media")

    def _probe_duration(self, path: Path) -> float:
        return 1.0


def _inputs(tmp_path: Path) -> list[SceneMedia]:
    clip = tmp_path / "shot.mp4"
    audio = tmp_path / "scene.mp3"
    clip.write_bytes(b"clip")
    audio.write_bytes(b"audio")
    return [
        SceneMedia(
            scene_number=1,
            clip_paths=[str(clip)],
            narration_path=str(audio),
        )
    ]


def test_assemble_renders_scene_with_narration_and_writes_final(tmp_path):
    service = RecordingFFmpegService()
    output = tmp_path / "final" / "final_video.mp4"

    result = service.assemble(_inputs(tmp_path), str(output))

    assert result == str(output)
    assert output.read_bytes() == b"media"
    scene_command = service.commands[0]
    assert "-t" in scene_command
    assert any("tpad=stop_mode=clone" in value for value in scene_command)


def test_assemble_rejects_missing_input_file(tmp_path):
    service = RecordingFFmpegService()
    scene = SceneMedia(
        scene_number=1,
        clip_paths=[str(tmp_path / "missing.mp4")],
        narration_path=str(tmp_path / "missing.mp3"),
    )

    with pytest.raises(FileNotFoundError, match="missing.mp4"):
        service.assemble([scene], str(tmp_path / "final.mp4"))


def test_assemble_rejects_empty_scene_list(tmp_path):
    service = RecordingFFmpegService()

    with pytest.raises(ValueError, match="at least one scene"):
        service.assemble([], str(tmp_path / "final.mp4"))


def test_run_translates_nonzero_exit(monkeypatch):
    service = LocalFFmpegService(executable="ffmpeg-test")
    completed = subprocess.CompletedProcess(["ffmpeg-test"], 1, "", "bad codec")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)

    with pytest.raises(FFmpegError, match="bad codec"):
        service._run(["ffmpeg-test", "-version"], "probe")


def test_run_translates_launch_failure(monkeypatch):
    service = LocalFFmpegService(executable="missing-ffmpeg")

    def fail_to_launch(*args, **kwargs):
        raise FileNotFoundError("missing binary")

    monkeypatch.setattr(subprocess, "run", fail_to_launch)

    with pytest.raises(FFmpegError, match="Unable to launch FFmpeg"):
        service._run(["missing-ffmpeg", "-version"], "probe")


def test_probe_duration_parses_ffmpeg_metadata(monkeypatch, tmp_path):
    service = LocalFFmpegService(executable="ffmpeg-test")
    completed = subprocess.CompletedProcess(
        ["ffmpeg-test"],
        1,
        "",
        "Duration: 00:01:02.50, start: 0.000000, bitrate: 128 kb/s",
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)

    assert service._probe_duration(tmp_path / "voice.mp3") == 62.5


def test_probe_duration_rejects_missing_metadata(monkeypatch, tmp_path):
    service = LocalFFmpegService(executable="ffmpeg-test")
    completed = subprocess.CompletedProcess(
        ["ffmpeg-test"],
        1,
        "",
        "Invalid data found when processing input",
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)

    with pytest.raises(FFmpegError, match="Could not determine duration"):
        service._probe_duration(tmp_path / "voice.mp3")


def test_bundled_ffmpeg_creates_real_mp4(tmp_path):
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    clip = tmp_path / "clip.mp4"
    audio = tmp_path / "voice.mp3"
    subprocess.run(
        [
            executable,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=1280x720:d=0.4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(clip),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            executable,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.6",
            "-q:a",
            "4",
            str(audio),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    output = tmp_path / "final.mp4"
    service = LocalFFmpegService(executable=executable)

    service.assemble(
        [
            SceneMedia(
                scene_number=1,
                clip_paths=[str(clip)],
                narration_path=str(audio),
            )
        ],
        str(output),
    )

    assert output.exists()
    assert output.stat().st_size > 1_000
    reader = imageio_ffmpeg.read_frames(str(output))
    metadata = next(reader)
    reader.close()
    assert metadata["duration"] >= 0.55


def test_bundled_ffmpeg_concatenates_multiple_scenes(tmp_path):
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    clip = tmp_path / "clip.mp4"
    audio = tmp_path / "voice.mp3"
    subprocess.run(
        [
            executable,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=1280x720:d=0.2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(clip),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            executable,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=330:duration=0.3",
            "-q:a",
            "4",
            str(audio),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    scenes = [
        SceneMedia(
            scene_number=number,
            clip_paths=[str(clip)],
            narration_path=str(audio),
        )
        for number in (1, 2)
    ]
    output = tmp_path / "two-scenes.mp4"

    LocalFFmpegService(executable=executable).assemble(scenes, str(output))

    assert output.is_file()
    assert output.stat().st_size > 1_000
