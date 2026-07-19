"""API request/response schemas — Pydantic models for the HTTP layer."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from models.agent_result import AgentResult, ArtifactRef
from models.enums import AgentName, JobStatus


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=5000)

    @field_validator("prompt")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt must not be empty or whitespace-only")
        return v


class GenerateResponse(BaseModel):
    job_id: str


class StatusResponse(BaseModel):
    job_id: str
    prompt: str
    status: JobStatus
    current_agent: AgentName | None = None
    failed_agent: AgentName | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class ResultResponse(BaseModel):
    job_id: str
    status: JobStatus
    output_path: str
    download_url: str
    artifacts: list[ArtifactRef]


class ResumeResponse(BaseModel):
    job_id: str


class JobDetailsResponse(BaseModel):
    job_id: str
    prompt: str
    status: JobStatus
    current_agent: AgentName | None = None
    failed_agent: AgentName | None = None
    error: str | None = None
    agent_results: dict[AgentName, AgentResult]
