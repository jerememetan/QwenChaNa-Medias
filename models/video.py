"""Video agent output models."""

from pydantic import BaseModel, Field


class VideoClip(BaseModel):
    """A generated video clip for a single storyboard shot."""

    shot_number: int = Field(ge=1)
    file_path: str
    duration: float | None = None


class VideoOutput(BaseModel):
    """Aggregate output produced by the Video Agent."""

    clips: list[VideoClip] = Field(default_factory=list)