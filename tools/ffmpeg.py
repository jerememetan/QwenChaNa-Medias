"""FFmpeg-based assembly for the Editor Agent."""

from abc import ABC, abstractmethod
from pathlib import Path
import shutil
import subprocess
import tempfile

import imageio_ffmpeg

from models.editor import SceneMedia


class FFmpegError(RuntimeError):
    """Raised when local media assembly fails."""


class FFmpegService(ABC):
    """Media assembly interface injected into Editor Agent."""

    @abstractmethod
    def assemble(self, scenes: list[SceneMedia], output_path: str) -> str:
        """Assemble ordered scene media into one MP4."""
        ...


class LocalFFmpegService(FFmpegService):
    """Render narration-led 1280x720 scene segments using local FFmpeg."""

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or imageio_ffmpeg.get_ffmpeg_exe()

    def assemble(self, scenes: list[SceneMedia], output_path: str) -> str:
        if not scenes:
            raise ValueError("FFmpeg assembly requires at least one scene")
        self._validate_inputs(scenes)

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="assembly-", dir=output.parent
        ) as temp_name:
            temp_dir = Path(temp_name)
            rendered: list[Path] = []
            for index, scene in enumerate(scenes, start=1):
                scene_path = temp_dir / f"scene_{index:03d}.mp4"
                self._render_scene(scene, scene_path)
                rendered.append(scene_path)
            self._concat_scenes(rendered, output)

        if not output.is_file() or output.stat().st_size == 0:
            raise FFmpegError(f"FFmpeg did not create a non-empty output: {output}")
        return str(output)

    @staticmethod
    def _validate_inputs(scenes: list[SceneMedia]) -> None:
        for scene in scenes:
            for raw_path in [*scene.clip_paths, scene.narration_path]:
                path = Path(raw_path)
                if not path.is_file():
                    raise FileNotFoundError(
                        f"Editor input file does not exist: {path}"
                    )

    def _render_scene(self, scene: SceneMedia, output: Path) -> None:
        command = [self.executable, "-y"]
        for clip_path in scene.clip_paths:
            command.extend(["-i", clip_path])
        audio_index = len(scene.clip_paths)
        command.extend(["-i", scene.narration_path])

        normalized: list[str] = []
        filters: list[str] = []
        video_filter = (
            "scale=1280:720:force_original_aspect_ratio=decrease,"
            "pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,"
            "fps=30,setpts=PTS-STARTPTS"
        )
        for index in range(len(scene.clip_paths)):
            label = f"v{index}"
            filters.append(f"[{index}:v:0]{video_filter}[{label}]")
            normalized.append(f"[{label}]")

        if len(normalized) == 1:
            filters.append(
                f"{normalized[0]}"
                "tpad=stop_mode=clone:stop_duration=3600[scene_v]"
            )
        else:
            filters.append(
                f"{''.join(normalized)}"
                f"concat=n={len(normalized)}:v=1:a=0[joined_v]"
            )
            filters.append(
                "[joined_v]tpad=stop_mode=clone:stop_duration=3600[scene_v]"
            )
        filters.append(
            f"[{audio_index}:a:0]aresample=48000,"
            "aformat=sample_fmts=fltp:channel_layouts=stereo,"
            "asetpts=PTS-STARTPTS[scene_a]"
        )

        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[scene_v]",
                "-map",
                "[scene_a]",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-shortest",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        self._run(command, f"render scene {scene.scene_number}")

    def _concat_scenes(self, scene_paths: list[Path], output: Path) -> None:
        if len(scene_paths) == 1:
            shutil.copy2(scene_paths[0], output)
            return

        command = [self.executable, "-y"]
        for scene_path in scene_paths:
            command.extend(["-i", str(scene_path)])
        streams = "".join(
            f"[{index}:v:0][{index}:a:0]" for index in range(len(scene_paths))
        )
        command.extend(
            [
                "-filter_complex",
                f"{streams}concat=n={len(scene_paths)}:v=1:a=1[final_v][final_a]",
                "-map",
                "[final_v]",
                "-map",
                "[final_a]",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
                "-c:a",
                "aac",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        self._run(command, "concatenate scenes")

    def _run(self, command: list[str], operation: str) -> None:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise FFmpegError(
                f"Unable to launch FFmpeg for {operation}: {exc}"
            ) from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip()[-2000:] or "no stderr output"
            raise FFmpegError(f"FFmpeg failed to {operation}: {detail}")
