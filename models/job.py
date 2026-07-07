from datetime import datetime, timezone

from pydantic import BaseModel, Field

from models.enums import AgentName, JobStatus


class JobRecord(BaseModel):
    job_id: str
    prompt: str
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    failed_agent: AgentName | None = None
    error: str | None = None
