"""Layer 9: API Routes tests — verify HTTP endpoints using FastAPI TestClient."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from agents.director import DirectorAgent
from agents.research import ResearchAgent
from agents.script import ScriptAgent
from agents.storyboard import StoryboardAgent
from backend.api.routes import create_app
from models.enums import AgentName, JobStatus
from models.job import JobRecord
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from tools.llm import LLMService


class InMemoryStorage(StorageBackend):
    """In-memory storage for route tests — no filesystem needed."""

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    def _key(self, job_id: str, agent_name: str, filename: str) -> str:
        return f"{job_id}/{agent_name}/{filename}"

    def save(self, job_id: str, agent_name: str, filename: str, data: dict) -> None:
        self._data[self._key(job_id, agent_name, filename)] = data

    def load(self, job_id: str, agent_name: str, filename: str) -> dict | None:
        return self._data.get(self._key(job_id, agent_name, filename))

    def exists(self, job_id: str, agent_name: str, filename: str) -> bool:
        return self._key(job_id, agent_name, filename) in self._data

    def list_artifacts(self, job_id: str, agent_name: str) -> list[str]:
        prefix = f"{job_id}/{agent_name}/"
        return [k.split("/")[-1] for k in self._data if k.startswith(prefix)]


def _make_test_app():
    """Create a test app with in-memory storage and job store."""
    storage = InMemoryStorage()
    job_store: dict[str, JobRecord] = {}
    app = create_app(storage=storage, job_store=job_store)
    client = TestClient(app)
    return client, storage, job_store


class TestGenerateEndpoint:
    def test_generate_returns_202_with_job_id(self):
        client, _, job_store = _make_test_app()
        response = client.post("/generate", json={"prompt": "Create a video about AI"})
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data

    def test_generate_returns_422_for_empty_prompt(self):
        client, _, _ = _make_test_app()
        response = client.post("/generate", json={"prompt": ""})
        assert response.status_code == 422

    def test_generate_returns_422_for_missing_prompt(self):
        client, _, _ = _make_test_app()
        response = client.post("/generate", json={})
        assert response.status_code == 422

    def test_generate_returns_422_for_oversized_prompt(self):
        client, _, _ = _make_test_app()
        response = client.post("/generate", json={"prompt": "x" * 5001})
        assert response.status_code == 422

    def test_generate_creates_job_record(self):
        client, _, job_store = _make_test_app()
        response = client.post("/generate", json={"prompt": "test video"})
        job_id = response.json()["job_id"]
        assert job_id in job_store
        assert job_store[job_id].status == JobStatus.PENDING


class TestStatusEndpoint:
    def test_status_returns_job_info(self):
        client, _, job_store = _make_test_app()
        # Create a job first
        gen_response = client.post("/generate", json={"prompt": "test video"})
        job_id = gen_response.json()["job_id"]
        # Check status
        response = client.get(f"/status/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["prompt"] == "test video"
        assert data["status"] == "pending"

    def test_status_returns_404_for_unknown_job(self):
        client, _, _ = _make_test_app()
        response = client.get("/status/nonexistent-id")
        assert response.status_code == 404


class TestResultEndpoint:
    def test_result_returns_output_for_completed_job(self):
        client, storage, job_store = _make_test_app()
        gen_response = client.post("/generate", json={"prompt": "test video"})
        job_id = gen_response.json()["job_id"]
        # Mark job as completed
        job_store[job_id].status = JobStatus.COMPLETED
        # Save context to storage so result can find output path
        ctx = WorkflowState(job_id=job_id, prompt="test video")
        ctx.status = JobStatus.COMPLETED
        storage.save(job_id, "pipeline", "context.json", ctx.model_dump(mode="json"))
        # Check result
        response = client.get(f"/result/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "completed"

    def test_result_returns_404_for_unknown_job(self):
        client, _, _ = _make_test_app()
        response = client.get("/result/nonexistent-id")
        assert response.status_code == 404

    def test_result_returns_409_for_non_completed_job(self):
        client, _, job_store = _make_test_app()
        gen_response = client.post("/generate", json={"prompt": "test video"})
        job_id = gen_response.json()["job_id"]
        # Job is still pending
        response = client.get(f"/result/{job_id}")
        assert response.status_code == 409


class TestResumeEndpoint:
    def test_resume_returns_202(self):
        client, storage, job_store = _make_test_app()
        gen_response = client.post("/generate", json={"prompt": "test video"})
        job_id = gen_response.json()["job_id"]
        # Mark job as failed
        job_store[job_id].status = JobStatus.FAILED
        # Save context so resume can load it
        ctx = WorkflowState(job_id=job_id, prompt="test video")
        ctx.status = JobStatus.FAILED
        ctx.failed_agent = AgentName.RESEARCH
        ctx.error = "Agent research failed"
        storage.save(job_id, "pipeline", "context.json", ctx.model_dump(mode="json"))
        # Resume
        response = client.post(f"/resume/{job_id}")
        assert response.status_code == 202
        assert response.json()["job_id"] == job_id

    def test_resume_returns_404_for_unknown_job(self):
        client, _, _ = _make_test_app()
        response = client.post("/resume/nonexistent-id")
        assert response.status_code == 404

    def test_resume_returns_409_for_running_job(self):
        client, _, job_store = _make_test_app()
        gen_response = client.post("/generate", json={"prompt": "test video"})
        job_id = gen_response.json()["job_id"]
        job_store[job_id].status = JobStatus.RUNNING
        response = client.post(f"/resume/{job_id}")
        assert response.status_code == 409

    def test_resume_returns_409_for_completed_job(self):
        client, _, job_store = _make_test_app()
        gen_response = client.post("/generate", json={"prompt": "test video"})
        job_id = gen_response.json()["job_id"]
        job_store[job_id].status = JobStatus.COMPLETED
        response = client.post(f"/resume/{job_id}")
        assert response.status_code == 409


def _mock_llm_service(*responses: str) -> MagicMock:
    mock = MagicMock(spec=LLMService)
    mock.generate.side_effect = responses
    return mock


class TestGeneratePipelineExecution:
    def test_generate_runs_pipeline_and_returns_completed_status(self):
        """POST /generate with agents should run all 4 agents and return a completed job."""
        brief_json = '{"title":"AI Explainer","prompt":"Make an AI video","tone":"informative","audience":"general","duration_seconds":30.0,"summary":"AI overview"}'
        research_json = '{"brief_summary":"AI overview","notes":[],"overall_confidence":0.7}'
        script_json = '{"title":"AI Explainer","scenes":[{"scene_number":1,"narration":"AI transforms the world","duration_hint":15.0,"visual_direction":"Show AI systems"}]}'
        storyboard_json = '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"AI lab","camera":"medium","motion":"pan","duration":15.0}]}'

        mock_llm = _mock_llm_service(brief_json, research_json, script_json, storyboard_json)
        storage = InMemoryStorage()
        job_store: dict[str, JobRecord] = {}

        agents = [
            DirectorAgent(llm_service=mock_llm, storage=storage),
            ResearchAgent(llm_service=mock_llm, storage=storage),
            ScriptAgent(llm_service=mock_llm, storage=storage),
            StoryboardAgent(llm_service=mock_llm, storage=storage),
        ]

        app = create_app(storage=storage, job_store=job_store, agents=agents)
        client = TestClient(app)

        resp = client.post("/generate", json={"prompt": "Make an AI video"})
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        status_resp = client.get(f"/status/{job_id}")
        assert status_resp.json()["status"] == "completed"


class TestStatusConsistency:
    def test_status_reflects_pipeline_completed_state(self):
        """When pipeline completes, /status should return 'completed'."""
        brief_json = '{"title":"T","prompt":"P","tone":"t","audience":"a","duration_seconds":10.0,"summary":"s"}'
        research_json = '{"brief_summary":"s","notes":[],"overall_confidence":0.5}'
        script_json = '{"title":"T","scenes":[{"scene_number":1,"narration":"n","duration_hint":5.0,"visual_direction":"v"}]}'
        storyboard_json = '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"v","camera":"c","motion":"m","duration":5.0}]}'

        mock_llm = _mock_llm_service(brief_json, research_json, script_json, storyboard_json)
        storage = InMemoryStorage()
        job_store: dict[str, JobRecord] = {}
        agents = [
            DirectorAgent(llm_service=mock_llm, storage=storage),
            ResearchAgent(llm_service=mock_llm, storage=storage),
            ScriptAgent(llm_service=mock_llm, storage=storage),
            StoryboardAgent(llm_service=mock_llm, storage=storage),
        ]
        app = create_app(storage=storage, job_store=job_store, agents=agents)
        client = TestClient(app)

        resp = client.post("/generate", json={"prompt": "test prompt"})
        job_id = resp.json()["job_id"]

        status_resp = client.get(f"/status/{job_id}")
        data = status_resp.json()
        assert data["status"] == "completed"

    def test_status_reflects_pipeline_failed_state(self):
        """When an agent fails, /status should return 'failed' with failed_agent."""
        mock_llm = MagicMock(spec=LLMService)
        mock_llm.generate.side_effect = RuntimeError("LLM timeout")

        storage = InMemoryStorage()
        job_store: dict[str, JobRecord] = {}
        agents = [
            DirectorAgent(llm_service=mock_llm, storage=storage),
        ]
        app = create_app(storage=storage, job_store=job_store, agents=agents)
        client = TestClient(app)

        resp = client.post("/generate", json={"prompt": "test prompt"})
        job_id = resp.json()["job_id"]

        status_resp = client.get(f"/status/{job_id}")
        data = status_resp.json()
        assert data["status"] == "failed"
        assert data["failed_agent"] == "director"

    def test_result_returns_200_for_completed_job_with_artifacts(self):
        """When pipeline completes, /result should return artifacts from all agents."""
        brief_json = '{"title":"T","prompt":"P","tone":"t","audience":"a","duration_seconds":10.0,"summary":"s"}'
        research_json = '{"brief_summary":"s","notes":[],"overall_confidence":0.5}'
        script_json = '{"title":"T","scenes":[{"scene_number":1,"narration":"n","duration_hint":5.0,"visual_direction":"v"}]}'
        storyboard_json = '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"v","camera":"c","motion":"m","duration":5.0}]}'

        mock_llm = _mock_llm_service(brief_json, research_json, script_json, storyboard_json)
        storage = InMemoryStorage()
        job_store: dict[str, JobRecord] = {}
        agents = [
            DirectorAgent(llm_service=mock_llm, storage=storage),
            ResearchAgent(llm_service=mock_llm, storage=storage),
            ScriptAgent(llm_service=mock_llm, storage=storage),
            StoryboardAgent(llm_service=mock_llm, storage=storage),
        ]
        app = create_app(storage=storage, job_store=job_store, agents=agents)
        client = TestClient(app)

        resp = client.post("/generate", json={"prompt": "test"})
        job_id = resp.json()["job_id"]

        result_resp = client.get(f"/result/{job_id}")
        assert result_resp.status_code == 200
        data = result_resp.json()
        assert data["status"] == "completed"
        assert len(data["artifacts"]) == 4
