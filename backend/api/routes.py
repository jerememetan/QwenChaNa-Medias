"""API routes — FastAPI endpoints for generate, status, result, resume."""

import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, Path as PathParam
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agents.base import BaseAgent
from backend.api.schemas import (
    GenerateRequest,
    GenerateResponse,
    JobDetailsResponse,
    ResumeResponse,
    ResultResponse,
    StatusResponse,
)
from models.editor import EditorOutput
from models.enums import AgentName, JobStatus
from models.job import JobRecord
from models.video import VideoOutput
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from workflow.pipeline import Pipeline
from workflow.resume import resume_job


def create_app(
    storage: StorageBackend,
    job_store: dict[str, JobRecord],
    agents: list[BaseAgent] | None = None,
    agent_factory: Callable[[], list[BaseAgent]] | None = None,
    frontend_dist: str | Path | None = None,
) -> FastAPI:
    app = FastAPI()
    pipeline = Pipeline(storage) if agents else None
    resume_transition_lock = Lock()

    def completed_editor_output(job_id: str) -> EditorOutput:
        record = job_store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if record.status != JobStatus.COMPLETED:
            raise HTTPException(
                status_code=409,
                detail=f"Job is {record.status.value}, not completed",
            )
        context_data = storage.load(job_id, "pipeline", "context.json")
        if context_data is None:
            raise HTTPException(status_code=404, detail="Job context not found")
        context = WorkflowState.model_validate(context_data)
        editor_result = context.agent_results.get(AgentName.EDITOR)
        if editor_result is None or not editor_result.success:
            raise HTTPException(status_code=404, detail="Final video result not found")
        return EditorOutput.model_validate(editor_result.output_data)

    @app.post("/generate", status_code=202, response_model=GenerateResponse)
    def generate(req: GenerateRequest) -> GenerateResponse:
        job_id = str(uuid.uuid4())
        job_record = JobRecord(job_id=job_id, prompt=req.prompt)
        job_store[job_id] = job_record
        ctx = WorkflowState(job_id=job_id, prompt=req.prompt)

        if pipeline is not None:
            ctx = pipeline.run(job_id, agents, ctx)
            job_record.status = ctx.status
            job_record.updated_at = ctx.updated_at
            if ctx.failed_agent:
                job_record.failed_agent = ctx.failed_agent
            if ctx.error:
                job_record.error = ctx.error

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

    @app.get("/details/{job_id}", response_model=JobDetailsResponse)
    def details(job_id: str) -> JobDetailsResponse:
        record = job_store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        context_data = storage.load(job_id, "pipeline", "context.json")
        if context_data is None:
            raise HTTPException(status_code=404, detail="Job context not found")
        context = WorkflowState.model_validate(context_data)
        return JobDetailsResponse(
            job_id=context.job_id,
            prompt=context.prompt,
            status=context.status,
            current_agent=context.current_agent,
            failed_agent=context.failed_agent,
            error=context.error,
            agent_results=context.agent_results,
        )

    @app.get("/result/{job_id}", response_model=ResultResponse)
    def result(job_id: str) -> ResultResponse:
        record = job_store.get(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        editor_output = completed_editor_output(job_id)
        artifacts = []
        context_data = storage.load(job_id, "pipeline", "context.json")
        if context_data is not None:
            ctx = WorkflowState.model_validate(context_data)
            for agent_result in ctx.agent_results.values():
                artifacts.extend(agent_result.artifacts)
        return ResultResponse(
            job_id=record.job_id,
            status=record.status,
            output_path=editor_output.final_path,
            download_url=f"/result/{job_id}/download",
            artifacts=artifacts,
        )

    @app.get("/result/{job_id}/clips/{shot_number}")
    def download_clip(
        job_id: str,
        shot_number: int = PathParam(ge=1),
    ) -> FileResponse:
        if job_id not in job_store:
            raise HTTPException(status_code=404, detail="Job not found")
        context_data = storage.load(job_id, "pipeline", "context.json")
        if context_data is None:
            raise HTTPException(status_code=404, detail="Job context not found")
        context = WorkflowState.model_validate(context_data)
        video_result = context.agent_results.get(AgentName.VIDEO)
        if video_result is None or not video_result.success:
            raise HTTPException(status_code=404, detail="Video clip not found")
        video = VideoOutput.model_validate(video_result.output_data)
        clip = next(
            (item for item in video.clips if item.shot_number == shot_number),
            None,
        )
        if clip is None:
            raise HTTPException(status_code=404, detail="Video clip not found")
        clip_path = Path(clip.file_path)
        if not clip_path.is_file():
            raise HTTPException(
                status_code=404,
                detail="Video clip file not found",
            )
        return FileResponse(
            path=clip_path,
            media_type="video/mp4",
            filename=f"shot-{shot_number:02d}.mp4",
            content_disposition_type="inline",
        )

    @app.get("/result/{job_id}/download")
    def download_result(job_id: str) -> FileResponse:
        editor_output = completed_editor_output(job_id)
        final_path = Path(editor_output.final_path)
        if not final_path.is_file():
            raise HTTPException(status_code=404, detail="Final video file not found")
        return FileResponse(
            path=final_path,
            media_type="video/mp4",
            filename="final_video.mp4",
        )

    @app.post("/resume/{job_id}", status_code=202, response_model=ResumeResponse)
    def resume(job_id: str) -> ResumeResponse:
        with resume_transition_lock:
            record = job_store.get(job_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Job not found")
            if record.status == JobStatus.RUNNING:
                raise HTTPException(status_code=409, detail="Job is already running")
            if record.status == JobStatus.COMPLETED:
                raise HTTPException(status_code=409, detail="Job is already completed")
            if storage.load(job_id, "pipeline", "context.json") is None:
                raise HTTPException(status_code=404, detail="Job context not found")
            resume_agents = agent_factory() if agent_factory is not None else agents
            if not resume_agents:
                raise HTTPException(
                    status_code=503,
                    detail="Resume is unavailable: no agents configured",
                )
            record.status = JobStatus.RUNNING
            record.updated_at = datetime.now(timezone.utc)
            record.failed_agent = None
            record.error = None

        try:
            context = resume_job(job_id, resume_agents, storage)
        except FileNotFoundError as exc:
            record.status = JobStatus.FAILED
            record.updated_at = datetime.now(timezone.utc)
            record.error = str(exc)
            raise HTTPException(status_code=404, detail="Job context not found") from exc
        record.status = context.status
        record.updated_at = context.updated_at
        record.failed_agent = context.failed_agent
        record.error = context.error
        return ResumeResponse(job_id=job_id)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    if frontend_dist is not None:
        frontend_path = Path(frontend_dist)
        if frontend_path.is_dir():
            app.mount(
                "/",
                StaticFiles(directory=frontend_path, html=True),
                name="frontend",
            )

    return app
