from pydantic import BaseModel, Field

from models.enums import AgentName


class ArtifactRef(BaseModel):
    agent_name: AgentName
    filename: str
    content_type: str
    size_bytes: int | None = None


class AgentResult(BaseModel):
    agent_name: AgentName
    success: bool
    output_data: dict = Field(default_factory=dict)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    error: str | None = None
    duration_seconds: float | None = None
