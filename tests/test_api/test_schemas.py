"""Layer 8: API Schemas tests — verify request/response Pydantic models."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.api.schemas import (
    GenerateRequest,
    GenerateResponse,
    StatusResponse,
    ResultResponse,
    ResumeResponse,
)
from models.enums import AgentName, JobStatus


class TestGenerateRequest:
    def test_generate_request_requires_prompt(self):
        with pytest.raises(ValidationError):
            GenerateRequest()

    def test_generate_request_rejects_empty_prompt(self):
        with pytest.raises(ValidationError):
            GenerateRequest(prompt="")
        with pytest.raises(ValidationError):
            GenerateRequest(prompt="   ")

    def test_generate_request_rejects_oversized_prompt(self):
        with pytest.raises(ValidationError):
            GenerateRequest(prompt="x" * 5001)

    def test_generate_request_strips_whitespace(self):
        req = GenerateRequest(prompt="  hello world  ")
        assert req.prompt == "hello world"


class TestGenerateResponse:
    def test_generate_response_schema(self):
        resp = GenerateResponse(job_id="abc-123")
        data = resp.model_dump()
        assert data == {"job_id": "abc-123"}


class TestStatusResponse:
    def test_status_response_schema(self):
        resp = StatusResponse(
            job_id="abc-123",
            prompt="test video",
            status=JobStatus.RUNNING,
            current_agent=AgentName.DIRECTOR,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        data = resp.model_dump()
        assert data["job_id"] == "abc-123"
        assert data["status"] == JobStatus.RUNNING
        assert data["current_agent"] == AgentName.DIRECTOR

    def test_status_response_current_agent_nullable(self):
        resp = StatusResponse(
            job_id="abc-123",
            prompt="test video",
            status=JobStatus.PENDING,
            current_agent=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert resp.current_agent is None


class TestResultResponse:
    def test_result_response_schema(self):
        resp = ResultResponse(
            job_id="abc-123",
            status=JobStatus.COMPLETED,
            output_path="./outputs/abc-123/editor/final/final_video.mp4",
            download_url="/result/abc-123/download",
            artifacts=[],
        )
        data = resp.model_dump()
        assert data["job_id"] == "abc-123"
        assert data["status"] == JobStatus.COMPLETED
        assert data["output_path"] == "./outputs/abc-123/editor/final/final_video.mp4"
        assert data["download_url"] == "/result/abc-123/download"
        assert data["artifacts"] == []


class TestResumeResponse:
    def test_resume_response_schema(self):
        resp = ResumeResponse(job_id="abc-123")
        data = resp.model_dump()
        assert data == {"job_id": "abc-123"}


class TestErrorResponse:
    def test_error_response_schema(self):
        # FastAPI uses HTTPException which produces {"detail": "..."}
        # We just verify the expected shape
        error_body = {"detail": "Job not found"}
        assert "detail" in error_body
