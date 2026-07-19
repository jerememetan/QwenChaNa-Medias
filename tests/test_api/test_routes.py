"""Layer 9: API Routes tests — verify HTTP endpoints using FastAPI TestClient."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from agents.base import BaseAgent
from agents.director import DirectorAgent
from agents.research import ResearchAgent
from agents.script import ScriptAgent
from agents.storyboard import StoryboardAgent
from backend.api.routes import create_app
from models.agent_result import AgentResult, ArtifactRef
from models.editor import EditorOutput
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


def _complete_with_editor_result(client, storage, job_store, tmp_path):
    response = client.post("/generate", json={"prompt": "test video"})
    job_id = response.json()["job_id"]
    final_path = tmp_path / job_id / "editor" / "final" / "final_video.mp4"
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_bytes(b"final-mp4")
    output = EditorOutput(final_path=str(final_path), scene_count=1)
    context = WorkflowState(
        job_id=job_id,
        prompt="test video",
        status=JobStatus.COMPLETED,
    )
    context.agent_results[AgentName.EDITOR] = AgentResult(
        agent_name=AgentName.EDITOR,
        success=True,
        output_data=output.model_dump(mode="json"),
        artifacts=[
            ArtifactRef(
                agent_name=AgentName.EDITOR,
                filename="final/final_video.mp4",
                content_type="video/mp4",
                size_bytes=9,
            )
        ],
    )
    storage.save(
        job_id,
        "pipeline",
        "context.json",
        context.model_dump(mode="json"),
    )
    job_store[job_id].status = JobStatus.COMPLETED
    return job_id, final_path


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
    def test_result_returns_output_for_completed_job(self, tmp_path):
        client, storage, job_store = _make_test_app()
        job_id, final_path = _complete_with_editor_result(
            client,
            storage,
            job_store,
            tmp_path,
        )
        response = client.get(f"/result/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "completed"
        assert data["output_path"] == str(final_path)
        assert data["download_url"] == f"/result/{job_id}/download"

    def test_download_returns_final_mp4(self, tmp_path):
        client, storage, job_store = _make_test_app()
        job_id, _ = _complete_with_editor_result(
            client,
            storage,
            job_store,
            tmp_path,
        )

        response = client.get(f"/result/{job_id}/download")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("video/mp4")
        assert response.content == b"final-mp4"

    def test_download_returns_404_when_final_file_is_missing(self, tmp_path):
        client, storage, job_store = _make_test_app()
        job_id, final_path = _complete_with_editor_result(
            client,
            storage,
            job_store,
            tmp_path,
        )
        final_path.unlink()

        response = client.get(f"/result/{job_id}/download")

        assert response.status_code == 404

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

    def test_result_returns_404_when_completed_job_has_no_editor_result(self):
        client, storage, job_store = _make_test_app()
        response = client.post("/generate", json={"prompt": "test video"})
        job_id = response.json()["job_id"]
        job_store[job_id].status = JobStatus.COMPLETED
        context = WorkflowState(
            job_id=job_id,
            prompt="test video",
            status=JobStatus.COMPLETED,
        )
        storage.save(
            job_id,
            "pipeline",
            "context.json",
            context.model_dump(mode="json"),
        )

        response = client.get(f"/result/{job_id}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Final video result not found"

class TestResumeEndpoint:
    def test_resume_executes_remaining_agents_and_updates_job_status(self):
        storage = InMemoryStorage()
        job_store: dict[str, JobRecord] = {}
        call_order: list[AgentName] = []
        app = create_app(
            storage=storage,
            job_store=job_store,
            agents=[CompletingEditor(call_order)],
        )
        client = TestClient(app)
        job_id = _failed_editor_job(storage, job_store)

        response = client.post(f"/resume/{job_id}")

        assert response.status_code == 202
        assert call_order == [AgentName.EDITOR]
        assert job_store[job_id].status == JobStatus.COMPLETED
        assert job_store[job_id].failed_agent is None
        assert job_store[job_id].error is None

    def test_resume_builds_fresh_agents_from_factory(self):
        storage = InMemoryStorage()
        job_store: dict[str, JobRecord] = {}
        call_order: list[AgentName] = []
        fresh = [CompletingEditor(call_order)]
        factory = MagicMock(return_value=fresh)
        app = create_app(
            storage=storage,
            job_store=job_store,
            agents=[FailingIfCalledEditor()],
            agent_factory=factory,
        )
        client = TestClient(app)
        job_id = _failed_editor_job(storage, job_store)

        response = client.post(f"/resume/{job_id}")

        assert response.status_code == 202
        factory.assert_called_once_with()
        assert call_order == [AgentName.EDITOR]

    def test_resume_returns_503_without_configured_agents(self):
        storage = InMemoryStorage()
        job_store: dict[str, JobRecord] = {}
        app = create_app(storage=storage, job_store=job_store)
        client = TestClient(app)
        job_id = _failed_editor_job(storage, job_store)

        response = client.post(f"/resume/{job_id}")

        assert response.status_code == 503

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


class CompletingEditor(BaseAgent):
    """Record resume execution and finish Editor without media work."""

    name = AgentName.EDITOR

    def __init__(self, call_order: list[AgentName]) -> None:
        self.call_order = call_order
        super().__init__()

    def run(self, context: WorkflowState) -> WorkflowState:
        self.call_order.append(self.name)
        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data={"final_path": "final.mp4", "scene_count": 1},
        )
        return context


class FailingIfCalledEditor(BaseAgent):
    name = AgentName.EDITOR

    def run(self, context: WorkflowState) -> WorkflowState:
        raise AssertionError("stale agents used")


def _failed_editor_job(storage, job_store) -> str:
    job_id = "resume-editor-job"
    context = WorkflowState(
        job_id=job_id,
        prompt="test",
        status=JobStatus.FAILED,
        failed_agent=AgentName.EDITOR,
        error="FFmpeg unavailable",
    )
    storage.save(
        job_id,
        "pipeline",
        "context.json",
        context.model_dump(mode="json"),
    )
    job_store[job_id] = JobRecord(
        job_id=job_id,
        prompt="test",
        status=JobStatus.FAILED,
        failed_agent=AgentName.EDITOR,
        error="FFmpeg unavailable",
    )
    return job_id


class ResultEditorAgent(BaseAgent):
    """Write a deterministic final artifact for route integration tests."""

    name = AgentName.EDITOR

    def __init__(self, output_root: Path) -> None:
        self.output_root = output_root
        super().__init__()

    def run(self, context: WorkflowState) -> WorkflowState:
        final_path = (
            self.output_root
            / context.job_id
            / "editor"
            / "final"
            / "final_video.mp4"
        )
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_bytes(b"final-mp4")
        output = EditorOutput(final_path=str(final_path), scene_count=1)
        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data=output.model_dump(mode="json"),
            artifacts=[
                ArtifactRef(
                    agent_name=self.name,
                    filename="final/final_video.mp4",
                    content_type="video/mp4",
                )
            ],
        )
        return context


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

    def test_result_returns_200_for_completed_job_with_artifacts(self, tmp_path):
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
            ResultEditorAgent(tmp_path),
        ]
        app = create_app(storage=storage, job_store=job_store, agents=agents)
        client = TestClient(app)

        resp = client.post("/generate", json={"prompt": "test"})
        job_id = resp.json()["job_id"]

        result_resp = client.get(f"/result/{job_id}")
        assert result_resp.status_code == 200
        data = result_resp.json()
        assert data["status"] == "completed"
        assert len(data["artifacts"]) == 5
