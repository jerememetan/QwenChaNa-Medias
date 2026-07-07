from pydantic import BaseModel, Field

from models.scene import Scene


class Script(BaseModel):
    title: str
    scenes: list[Scene] = Field(min_length=1)
    total_estimated_duration: float | None = None
