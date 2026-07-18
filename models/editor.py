"""Editor Agent input and output models."""

from pydantic import BaseModel, Field


class SceneMedia(BaseModel):
    """Ordered visual clips and one narration track for a scene."""

    scene_number: int = Field(ge=1)
    clip_paths: list[str] = Field(min_length=1)
    narration_path: str = Field(min_length=1)


class EditorOutput(BaseModel):
    """Final media produced by the Editor Agent."""

    final_path: str = Field(min_length=1)
    scene_count: int = Field(ge=1)
