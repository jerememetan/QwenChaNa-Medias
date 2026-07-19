"""Editor Agent input and output models."""

from pydantic import BaseModel, Field


class ClipMedia(BaseModel):
    """One generated clip paired with its Storyboard timing."""

    shot_number: int = Field(ge=1)
    file_path: str = Field(min_length=1)
    planned_duration: float = Field(gt=0)


class SceneMedia(BaseModel):
    """Ordered clips, narration, and planned total for one scene."""

    scene_number: int = Field(ge=1)
    clips: list[ClipMedia] = Field(min_length=1)
    narration_path: str = Field(min_length=1)
    planned_duration: float = Field(gt=0)


class EditorOutput(BaseModel):
    """Final media produced by the Editor Agent."""

    final_path: str = Field(min_length=1)
    scene_count: int = Field(ge=1)
