"""Editor Agent — validates and assembles final narrated media."""

from collections import defaultdict
from pathlib import Path
from typing import Any

from models.agent_result import AgentResult, ArtifactRef
from models.editor import EditorOutput, SceneMedia
from models.enums import AgentName
from models.storyboard import Storyboard
from models.video import VideoOutput
from models.voice import VoiceOutput
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from tools.ffmpeg import FFmpegService


class EditorAgent:
    """Map generated assets to scenes and assemble the final MP4."""

    name = AgentName.EDITOR

    def __init__(
        self,
        ffmpeg_service: FFmpegService,
        storage: StorageBackend | None = None,
        output_dir: str | Path = "./outputs",
    ) -> None:
        self.ffmpeg_service = ffmpeg_service
        self.storage = storage
        self.output_dir = Path(output_dir)

    def run(self, context: WorkflowState) -> WorkflowState:
        for required in (AgentName.STORYBOARD, AgentName.VIDEO, AgentName.VOICE):
            if required not in context.agent_results:
                raise ValueError(
                    f"Editor agent requires {required.value} output in context"
                )

        storyboard = Storyboard.model_validate(
            context.agent_results[AgentName.STORYBOARD].output_data
        )
        video = VideoOutput.model_validate(
            context.agent_results[AgentName.VIDEO].output_data
        )
        voice = VoiceOutput.model_validate(
            context.agent_results[AgentName.VOICE].output_data
        )
        scenes = self._build_scene_media(storyboard, video, voice)

        output_path = (
            self.output_dir
            / context.job_id
            / "editor"
            / "final"
            / "final_video.mp4"
        )
        final_path = self.ffmpeg_service.assemble(scenes, str(output_path))
        final_file = Path(final_path)
        if not final_file.is_file():
            raise FileNotFoundError(
                f"Editor service did not create final video: {final_file}"
            )
        output = EditorOutput(final_path=final_path, scene_count=len(scenes))

        if self.storage is not None:
            self.storage.save(
                context.job_id,
                self.name.value,
                "editor_output.json",
                output.model_dump(mode="json"),
            )
        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data=output.model_dump(mode="json"),
            artifacts=[
                ArtifactRef(
                    agent_name=self.name,
                    filename="final/final_video.mp4",
                    content_type="video/mp4",
                    size_bytes=final_file.stat().st_size,
                )
            ],
        )
        return context

    @staticmethod
    def _unique_by(
        items: list[Any], attribute: str, label: str
    ) -> dict[int, Any]:
        indexed: dict[int, Any] = {}
        for item in items:
            key = getattr(item, attribute)
            if key in indexed:
                raise ValueError(f"Editor received duplicate {label} {key}")
            indexed[key] = item
        return indexed

    def _build_scene_media(
        self,
        storyboard: Storyboard,
        video: VideoOutput,
        voice: VoiceOutput,
    ) -> list[SceneMedia]:
        shots = self._unique_by(
            storyboard.shots,
            "shot_number",
            "storyboard shot",
        )
        clips = self._unique_by(
            video.clips,
            "shot_number",
            "video clip for shot",
        )
        tracks = self._unique_by(
            voice.tracks,
            "scene_number",
            "narration for scene",
        )
        missing_clips = sorted(set(shots) - set(clips))
        if missing_clips:
            raise ValueError(
                f"Editor is missing video clip for shot {missing_clips[0]}"
            )

        grouped: dict[int, list[str]] = defaultdict(list)
        scene_order: list[int] = []
        for shot in storyboard.shots:
            if shot.scene_number not in grouped:
                scene_order.append(shot.scene_number)
            grouped[shot.scene_number].append(
                clips[shot.shot_number].file_path
            )

        scenes: list[SceneMedia] = []
        for scene_number in scene_order:
            if scene_number not in tracks:
                raise ValueError(
                    f"Editor is missing narration for scene {scene_number}"
                )
            paths = [
                *grouped[scene_number],
                tracks[scene_number].file_path,
            ]
            missing_files = [path for path in paths if not Path(path).is_file()]
            if missing_files:
                raise FileNotFoundError(
                    f"Editor input file does not exist: {missing_files[0]}"
                )
            scenes.append(
                SceneMedia(
                    scene_number=scene_number,
                    clip_paths=grouped[scene_number],
                    narration_path=tracks[scene_number].file_path,
                )
            )
        return scenes
