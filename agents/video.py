"""Video agent — generates video clips from storyboard shots using Qwen wan2.7-t2v."""

from pathlib import Path

from models.enums import AgentName
from models.agent_result import AgentResult, ArtifactRef
from models.storyboard import Storyboard
from models.video import VideoClip, VideoOutput
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from tools.fallback_media import create_placeholder_video
from tools.video_gen import VideoGenService


class VideoAgent:
    """Generates video clips for each storyboard shot.

    Iterates over ``Storyboard.shots``, calls ``VideoGenService.generate``
    for each, persists clips beneath the configured output directory, and
    writes a ``VideoOutput`` into the agent result.

    Raises ``RuntimeError`` when the API is unavailable and
    ``fallback_enabled`` is ``False``.
    """

    name = AgentName.VIDEO

    def __init__(
        self,
        video_service: VideoGenService,
        storage: StorageBackend | None = None,
        fallback_enabled: bool = False,
        output_dir: str | Path = "./outputs",
    ) -> None:
        self.video_service = video_service
        self.storage = storage
        self.fallback_enabled = fallback_enabled
        self.output_dir = Path(output_dir)

    def _clip_path(self, job_id: str, shot_number: int) -> str:
        return str(
            self.output_dir
            / job_id
            / "video"
            / "clips"
            / f"shot_{shot_number:03d}.mp4"
        )

    @staticmethod
    def _is_reusable(clip: VideoClip) -> bool:
        path = Path(clip.file_path)
        return path.is_file() and path.stat().st_size > 0

    def _load_manifest(self, job_id: str) -> dict[int, VideoClip]:
        if self.storage is None:
            return {}
        data = self.storage.load(job_id, self.name.value, "video_output.json")
        if data is None:
            return {}
        output = VideoOutput.model_validate(data)
        return {clip.shot_number: clip for clip in output.clips}

    def _save_manifest(self, job_id: str, clips: list[VideoClip]) -> None:
        if self.storage is None:
            return
        output = VideoOutput(clips=clips)
        self.storage.save(
            job_id,
            self.name.value,
            "video_output.json",
            output.model_dump(mode="json"),
        )

    def run(self, context: WorkflowState) -> WorkflowState:
        """Generate a video clip for every shot in the storyboard.

        Args:
            context: Pipeline state containing at least a Storyboard result.

        Returns:
            Updated context with VideoOutput in ``agent_results[VIDEO]``.

        Raises:
            ValueError: If no Storyboard result is present in context.
            RuntimeError: If generation fails and fallback is disabled.
        """
        if AgentName.STORYBOARD not in context.agent_results:
            raise ValueError("Video agent requires Storyboard output in context")

        storyboard = Storyboard.model_validate(
            context.agent_results[AgentName.STORYBOARD].output_data
        )

        completed = self._load_manifest(context.job_id)
        clips: list[VideoClip] = []
        artifacts: list[ArtifactRef] = []

        for shot in storyboard.shots:
            existing = completed.get(shot.shot_number)
            if existing is not None and self._is_reusable(existing):
                clip = existing
            else:
                output_path = self._clip_path(context.job_id, shot.shot_number)
                try:
                    generated_path = self.video_service.generate(
                        shot.visual_prompt,
                        output_path,
                    )
                except Exception as exc:
                    if not self.fallback_enabled:
                        raise RuntimeError(
                            f"Video generation failed: {exc}. "
                            "Set FALLBACK_STUBS=true to generate placeholder media, "
                            "or configure VIDEO_API_KEY in .env."
                        ) from exc
                    generated_path = create_placeholder_video(
                        output_path,
                        shot.duration,
                    )

                clip = VideoClip(
                    shot_number=shot.shot_number,
                    file_path=generated_path,
                    duration=shot.duration,
                )
                if not self._is_reusable(clip):
                    raise RuntimeError(
                        "Video generation returned a missing or empty file: "
                        f"{generated_path}"
                    )
                completed[shot.shot_number] = clip
                ordered_partial = [
                    completed[item.shot_number]
                    for item in storyboard.shots
                    if item.shot_number in completed
                    and self._is_reusable(completed[item.shot_number])
                ]
                self._save_manifest(context.job_id, ordered_partial)

            clips.append(clip)
            artifacts.append(
                ArtifactRef(
                    agent_name=self.name,
                    filename=f"clips/shot_{shot.shot_number:03d}.mp4",
                    content_type="video/mp4",
                )
            )

        video_output = VideoOutput(clips=clips)

        self._save_manifest(context.job_id, clips)

        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data=video_output.model_dump(mode="json"),
            artifacts=artifacts,
        )
        return context
