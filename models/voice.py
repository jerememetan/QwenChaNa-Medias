"""Voice agent output models."""

from pydantic import BaseModel, Field


class AudioTrack(BaseModel):
    """A generated narration audio track for a single script scene."""

    scene_number: int = Field(ge=1)
    file_path: str
    duration: float | None = None


class VoiceOutput(BaseModel):
    """Aggregate output produced by the Voice Agent."""

    tracks: list[AudioTrack] = Field(default_factory=list)