"""API routes — FastAPI endpoints for generate, status, result, resume."""

import uuid

from fastapi import FastAPI, HTTPException

from backend.api.schemas import (
    GenerateRequest,
    GenerateResponse,
    ResumeResponse,
    ResultResponse,
    StatusResponse,
)
from models.enums import JobStatus
from models.job import JobRecord
from models.workflow_state import WorkflowState
from storage.base import StorageBackend


def create_app(
    storage: StorageBackend, job_store: dict[str, JobRecord]
) -> FastAPI:
    app = FastAPI()

    @app.post("/generate", status_code=202, response_model=GenerateResponse)
    def generate(req: GenerateRequest) -> GenerateResponse:
        job_id = str(uuid.uuid4())
        job_record = JobRecord(job_id=job_id, prompt=req.prompt)
        job_store[job_id] = job_record
        ctx = WorkflowState(job_id=job_id, prompt=req.prompt)
        storage.save(job_id, "pipeline", "context.json", ctx.model_dump(mode="json"))
        return GenerateResponse(job_id=job_id)

    @app.get("/status/{job_id}", response_model=StatusResponse)
    def status(job_id: str) -> StatusResponse:
        record = job_store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        context_data = storage.load(job_id, "pipeline", "context.json")
        current_agent = None
        failed_agent = None
        error = None
        if context_data is not None:
            ctx = WorkflowState.model_validate(context_data)
            current_agent = ctx.current_agent
            failed_agent = ctx.failed_agent
            error = ctx.error
        return StatusResponse(
            job_id=record.job_id,
            prompt=record.prompt,
            status=record.status,
            current_agent=current_agent,
            failed_agent=failed_agent,
            error=error,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @app.get("/result/{job_id}", response_model=ResultResponse)
    def result(job_id: str) -> ResultResponse:
        record = job_store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if record.status != JobStatus.COMPLETED:
            raise HTTPException(
                status_code=409,
                detail=f"Job is {record.status.value}, not completed",
            )
        return ResultResponse(
            job_id=record.job_id,
            status=record.status,
            output_path=f"./outputs/{job_id}",
            artifacts=[],
        )

    @app.post("/resume/{job_id}", status_code=202, response_model=ResumeResponse)
    def resume(job_id: str) -> ResumeResponse:
        record = job_store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if record.status == JobStatus.RUNNING:
            raise HTTPException(status_code=409, detail="Job is already running")
        if record.status == JobStatus.COMPLETED:
            raise HTTPException(status_code=409, detail="Job is already completed")
        return ResumeResponse(job_id=job_id)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app
