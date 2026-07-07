from pydantic import BaseModel, Field


class ResearchNote(BaseModel):
    topic: str
    content: str
    source: str | None = None
    verified: bool = False


class ResearchNotes(BaseModel):
    brief_summary: str
    notes: list[ResearchNote] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
