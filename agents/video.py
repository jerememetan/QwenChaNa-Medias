"""Video agent — generates video clips from storyboard shots using Qwen wan2.7-t2v."""

from pathlib import Path

from models.enums import AgentName
from models.agent_result import AgentResult, ArtifactRef
from models.storyboard import Storyboard
from models.video import VideoClip, VideoOutput
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from tools.video_gen import VideoGenService


class VideoAgent:
    """Generates video clips for each storyboard shot.

    Iterates over ``Storyboard.shots``, calls ``VideoGenService.generate``
    for each, persists clips to ``outputs/{job_id}/video/clips/``, and
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
    ) -> None:
        self.video_service = video_service
        self.storage = storage
        self.fallback_enabled = fallback_enabled

    def _clip_path(self, job_id: str, shot_number: int) -> str:
        return str(
            Path("outputs") / job_id / "video" / "clips" / f"shot_{shot_number:03d}.mp4"
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

        clips: list[VideoClip] = []
        artifacts: list[ArtifactRef] = []

        for shot in storyboard.shots:
            output_path = self._clip_path(context.job_id, shot.shot_number)
            try:
                generated_path = self.video_service.generate(shot.visual_prompt, output_path)
            except Exception as exc:
                if not self.fallback_enabled:
                    raise RuntimeError(
                        f"Video generation failed: {exc}. "
                        f"Set FALLBACK_STUBS=true to generate placeholder media, "
                        f"or configure VIDEO_API_KEY in .env."
                    ) from exc
                raise NotImplementedError(
                    "Fallback stub mode not implemented for VideoAgent"
                ) from exc

            clips.append(
                VideoClip(
                    shot_number=shot.shot_number,
                    file_path=generated_path,
                    duration=shot.duration,
                )
            )
            artifacts.append(
                ArtifactRef(
                    agent_name=self.name,
                    filename=f"clips/shot_{shot.shot_number:03d}.mp4",
                    content_type="video/mp4",
                )
            )

        video_output = VideoOutput(clips=clips)

        if self.storage is not None:
            self.storage.save(
                context.job_id,
                self.name.value,
                "video_output.json",
                video_output.model_dump(mode="json"),
            )

        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data=video_output.model_dump(mode="json"),
            artifacts=artifacts,
        )
        return context
