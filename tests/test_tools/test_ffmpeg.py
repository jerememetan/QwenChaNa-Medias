"""FFmpeg assembly service tests."""

from pathlib import Path
import subprocess

import imageio_ffmpeg
import pytest

from models.editor import ClipMedia, SceneMedia
from tools.ffmpeg import FFmpegError, LocalFFmpegService


class RecordingFFmpegService(LocalFFmpegService):
    """Record commands and create fake outputs without launching FFmpeg."""

    def __init__(self, narration_duration: float = 1.0):
        super().__init__(executable="ffmpeg-test")
        self.narration_duration = narration_duration
        self.commands: list[list[str]] = []

    def _run(self, command: list[str], operation: str) -> None:
        self.commands.append(command)
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_bytes(b"media")

    def _probe_duration(self, path: Path) -> float:
        return self.narration_duration


def _inputs(
    tmp_path: Path,
    planned_duration: float = 2.0,
) -> list[SceneMedia]:
    clip = tmp_path / "shot.mp4"
    audio = tmp_path / "scene.mp3"
    clip.write_bytes(b"clip")
    audio.write_bytes(b"audio")
    return [
        SceneMedia(
            scene_number=1,
            clips=[
                ClipMedia(
                    shot_number=1,
                    file_path=str(clip),
                    planned_duration=planned_duration,
                )
            ],
            narration_path=str(audio),
            planned_duration=planned_duration,
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


def test_render_trims_clip_and_uses_planned_duration_when_audio_is_short(
    tmp_path,
):
    service = RecordingFFmpegService(narration_duration=1.0)

    service.assemble(
        _inputs(tmp_path, planned_duration=2.0),
        str(tmp_path / "final.mp4"),
    )

    command = service.commands[0]
    filters = command[command.index("-filter_complex") + 1]
    assert "trim=duration=2.000000" in filters
    assert "tpad=stop_mode=clone" in filters
    assert "apad=whole_dur=2.000000" in filters
    assert command[command.index("-t") + 1] == "2.000000"


def test_render_uses_narration_duration_when_audio_is_longer(tmp_path):
    service = RecordingFFmpegService(narration_duration=3.0)

    service.assemble(
        _inputs(tmp_path, planned_duration=2.0),
        str(tmp_path / "final.mp4"),
    )

    command = service.commands[0]
    assert command[command.index("-t") + 1] == "3.000000"


def test_render_trims_every_clip_before_concat(tmp_path):
    first = tmp_path / "shot_001.mp4"
    second = tmp_path / "shot_002.mp4"
    audio = tmp_path / "scene.mp3"
    for path in (first, second, audio):
        path.write_bytes(b"media")
    scene = SceneMedia(
        scene_number=1,
        clips=[
            ClipMedia(
                shot_number=1,
                file_path=str(first),
                planned_duration=0.65,
            ),
            ClipMedia(
                shot_number=2,
                file_path=str(second),
                planned_duration=4.35,
            ),
        ],
        narration_path=str(audio),
        planned_duration=5.0,
    )
    service = RecordingFFmpegService(narration_duration=1.0)

    service.assemble([scene], str(tmp_path / "final.mp4"))

    command = service.commands[0]
    filters = command[command.index("-filter_complex") + 1]
    assert "trim=duration=0.650000" in filters
    assert "trim=duration=4.350000" in filters
    assert "concat=n=2:v=1:a=0" in filters
    assert command[command.index("-t") + 1] == "5.000000"


def test_assemble_rejects_missing_input_file(tmp_path):
    service = RecordingFFmpegService()
    scene = SceneMedia(
        scene_number=1,
        clips=[
            ClipMedia(
                shot_number=1,
                file_path=str(tmp_path / "missing.mp4"),
                planned_duration=1,
            )
        ],
        narration_path=str(tmp_path / "missing.mp3"),
        planned_duration=1,
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
            "color=c=blue:s=1280x720:d=0.8",
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
            "sine=frequency=440:duration=0.2",
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
                clips=[
                    ClipMedia(
                        shot_number=1,
                        file_path=str(clip),
                        planned_duration=0.5,
                    )
                ],
                narration_path=str(audio),
                planned_duration=0.5,
            )
        ],
        str(output),
    )

    assert output.exists()
    assert output.stat().st_size > 1_000
    reader = imageio_ffmpeg.read_frames(str(output))
    metadata = next(reader)
    reader.close()
    assert 0.45 <= metadata["duration"] <= 0.65
    probe = subprocess.run(
        [executable, "-hide_banner", "-i", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert "Audio:" in probe.stderr


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
            clips=[
                ClipMedia(
                    shot_number=number,
                    file_path=str(clip),
                    planned_duration=0.2,
                )
            ],
            narration_path=str(audio),
            planned_duration=0.2,
        )
        for number in (1, 2)
    ]
    output = tmp_path / "two-scenes.mp4"

    LocalFFmpegService(executable=executable).assemble(scenes, str(output))

    assert output.is_file()
    assert output.stat().st_size > 1_000
