from pydantic import BaseModel, Field


class Shot(BaseModel):
    shot_number: int = Field(ge=1)
    scene_number: int = Field(ge=1)
    visual_prompt: str
    camera: str
    motion: str
    duration: float = Field(gt=0)
    mood: str | None = None


class Storyboard(BaseModel):
    shots: list[Shot] = Field(min_length=1)
    total_duration: float | None = None
