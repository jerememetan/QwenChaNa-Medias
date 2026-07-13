"""Voice agent — generates narration audio tracks from a script using Qwen cosyvoice-v3-plus."""

from pathlib import Path

from models.enums import AgentName
from models.agent_result import AgentResult, ArtifactRef
from models.script import Script
from models.voice import AudioTrack, VoiceOutput
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from tools.tts import TTSService


class VoiceAgent:
    """Generates narration audio tracks for each script scene.

    Iterates over ``Script.scenes``, calls ``TTSService.synthesize``
    for each scene's narration, persists audio to
    ``outputs/{job_id}/voice/audio/``, and writes a ``VoiceOutput``
    into the agent result.

    Raises ``RuntimeError`` when the API is unavailable and
    ``fallback_enabled`` is ``False``.
    """

    name = AgentName.VOICE

    def __init__(
        self,
        tts_service: TTSService,
        storage: StorageBackend | None = None,
        fallback_enabled: bool = False,
    ) -> None:
        self.tts_service = tts_service
        self.storage = storage
        self.fallback_enabled = fallback_enabled

    def _track_path(self, job_id: str, scene_number: int) -> str:
        return str(
            Path("outputs") / job_id / "voice" / "audio" / f"scene_{scene_number:03d}.mp3"
        )

    def run(self, context: WorkflowState) -> WorkflowState:
        """Generate a narration track for every scene in the script.

        Args:
            context: Pipeline state containing at least a Script result.

        Returns:
            Updated context with VoiceOutput in ``agent_results[VOICE]``.

        Raises:
            ValueError: If no Script result is present in context.
            RuntimeError: If synthesis fails and fallback is disabled.
        """
        if AgentName.SCRIPT not in context.agent_results:
            raise ValueError("Voice agent requires Script output in context")

        script = Script.model_validate(
            context.agent_results[AgentName.SCRIPT].output_data
        )

        tracks: list[AudioTrack] = []
        artifacts: list[ArtifactRef] = []

        for scene in script.scenes:
            output_path = self._track_path(context.job_id, scene.scene_number)
            try:
                generated_path = self.tts_service.synthesize(scene.narration, output_path)
            except Exception as exc:
                if not self.fallback_enabled:
                    raise RuntimeError(
                        f"Voice synthesis failed: {exc}. "
                        f"Set FALLBACK_STUBS=true to generate placeholder media, "
                        f"or configure VOICE_API_KEY in .env."
                    ) from exc
                raise NotImplementedError(
                    "Fallback stub mode not implemented for VoiceAgent"
                ) from exc

            tracks.append(
                AudioTrack(
                    scene_number=scene.scene_number,
                    file_path=generated_path,
                    duration=scene.duration_hint,
                )
            )
            artifacts.append(
                ArtifactRef(
                    agent_name=self.name,
                    filename=f"audio/scene_{scene.scene_number:03d}.mp3",
                    content_type="audio/mpeg",
                )
            )

        voice_output = VoiceOutput(tracks=tracks)

        if self.storage is not None:
            self.storage.save(
                context.job_id,
                self.name.value,
                "voice_output.json",
                voice_output.model_dump(mode="json"),
            )

        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data=voice_output.model_dump(mode="json"),
            artifacts=artifacts,
        )
        return context
