from pydantic import BaseModel, Field


class Scene(BaseModel):
    scene_number: int = Field(ge=1)
    narration: str
    duration_hint: float = Field(gt=0)
    visual_direction: str
    mood: str | None = None
