from pydantic import BaseModel, Field


class CreativeBrief(BaseModel):
    title: str
    prompt: str
    tone: str
    audience: str
    duration_seconds: float = Field(gt=0)
    summary: str
    aspect_ratio: str = "16:9"
    style_keywords: list[str] = Field(default_factory=list)
