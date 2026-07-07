from datetime import datetime, timezone

from pydantic import BaseModel, Field

from models.agent_result import AgentResult
from models.enums import AgentName, JobStatus


class WorkflowState(BaseModel):
    job_id: str
    prompt: str
    status: JobStatus = JobStatus.PENDING
    current_agent: AgentName | None = None
    agent_results: dict[AgentName, AgentResult] = Field(default_factory=dict)
    failed_agent: AgentName | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
