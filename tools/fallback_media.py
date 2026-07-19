"""Generate valid local placeholder media when provider calls are unavailable."""

from pathlib import Path
import subprocess

import imageio_ffmpeg


class FallbackMediaError(RuntimeError):
    """Raised when FFmpeg cannot create fallback media."""


def _run(command: list[str], output_path: str) -> str:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise FallbackMediaError(f"Could not launch FFmpeg: {exc}") from exc
    invalid_output = (
        not output.is_file() or output.stat().st_size == 0
    )
    if completed.returncode != 0 or invalid_output:
        detail = completed.stderr.strip()[-1000:] or "no FFmpeg output"
        raise FallbackMediaError(f"Could not create fallback media: {detail}")
    return str(output)


def create_placeholder_video(output_path: str, duration: float) -> str:
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    return _run(
        [
            executable,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x171714:s=1280x720:r=30:d={duration:.6f}",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            output_path,
        ],
        output_path,
    )


def create_placeholder_audio(output_path: str, duration: float) -> str:
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    return _run(
        [
            executable,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-t",
            f"{duration:.6f}",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            output_path,
        ],
        output_path,
    )
