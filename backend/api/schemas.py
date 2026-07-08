from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from models.enums import AgentName, JobStatus


class GenerateRequest(BaseModel):
    """Request body for starting a new generation job."""

    prompt: str = Field(..., min_length=1, max_length=5000)

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        """Reject empty or whitespace-only prompts."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("Prompt must not be empty")
        return normalized


class GenerateResponse(BaseModel):
    """Acknowledgement payload returned immediately after job creation."""

    job_id: str
    status: JobStatus
    message: str


class StatusResponse(BaseModel):
    """Status payload returned by the polling endpoint."""

    job_id: str
    status: JobStatus
    current_agent: AgentName | None = None
    failed_agent: AgentName | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class ResultResponse(BaseModel):
    """Placeholder response for the result endpoint."""

    job_id: str
    status: JobStatus
    output_path: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    message: str


class ResumeResponse(BaseModel):
    """Placeholder response for the resume endpoint."""

    job_id: str
    status: JobStatus
    message: str
