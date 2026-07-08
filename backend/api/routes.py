from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from backend.api.schemas import (
    GenerateRequest,
    GenerateResponse,
    ResumeResponse,
    ResultResponse,
    StatusResponse,
)
from models.enums import JobStatus
from models.job import JobRecord

router = APIRouter()

_jobs: dict[str, JobRecord] = {}


@router.post("/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
def generate(request: GenerateRequest) -> GenerateResponse:
    """Create a placeholder job record and acknowledge the request."""

    job = JobRecord(job_id=str(uuid4()), prompt=request.prompt)
    _jobs[job.job_id] = job

    return GenerateResponse(
        job_id=job.job_id,
        status=job.status,
        message="Generation pipeline placeholder. Implementation pending.",
    )


@router.get("/status/{job_id}", response_model=StatusResponse)
def get_status(job_id: str) -> StatusResponse:
    """Return the current placeholder status for a known job."""

    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return StatusResponse(
        job_id=job.job_id,
        status=job.status,
        current_agent=None,
        failed_agent=job.failed_agent,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/result/{job_id}", response_model=ResultResponse)
def get_result(job_id: str) -> ResultResponse:
    """Return a placeholder result payload for a known job."""

    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return ResultResponse(
        job_id=job.job_id,
        status=job.status,
        output_path=None,
        artifacts=[],
        message="Result endpoint placeholder. Implementation pending.",
    )


@router.post("/resume/{job_id}", response_model=ResumeResponse, status_code=status.HTTP_202_ACCEPTED)
def resume_job(job_id: str) -> ResumeResponse:
    """Return a placeholder resume acknowledgement for a known job."""

    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return ResumeResponse(
        job_id=job.job_id,
        status=job.status,
        message="Resume flow placeholder. Implementation pending.",
    )
