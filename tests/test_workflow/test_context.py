"""Layer 5: JobContext tests — verify that JobContext (re-exported WorkflowState)
supports the Pydantic model operations used by the pipeline."""

from datetime import datetime, timezone

from models.agent_result import AgentResult
from models.enums import AgentName, JobStatus
from models.workflow_state import WorkflowState
from workflow.context import JobContext


class TestJobContextIdentity:
    def test_job_context_is_workflow_state(self):
        assert JobContext is WorkflowState


class TestJobContextCreation:
    def test_context_creation_defaults(self):
        ctx = JobContext(job_id="abc", prompt="test")
        assert ctx.status == JobStatus.PENDING
        assert ctx.agent_results == {}
        assert ctx.current_agent is None
        assert ctx.failed_agent is None
        assert ctx.error is None


class TestJobContextSerialization:
    def test_context_serializes_to_json(self):
        ctx = JobContext(job_id="abc", prompt="test")
        json_str = ctx.model_dump_json()
        assert isinstance(json_str, str)
        assert "abc" in json_str
        assert "pending" in json_str

    def test_context_deserializes_from_json(self):
        ctx = JobContext(job_id="abc", prompt="test")
        json_str = ctx.model_dump_json()
        restored = JobContext.model_validate_json(json_str)
        assert restored.job_id == ctx.job_id
        assert restored.prompt == ctx.prompt
        assert restored.status == ctx.status

    def test_context_agent_results_preserved_in_roundtrip(self):
        result = AgentResult(
            agent_name=AgentName.DIRECTOR, success=True, output_data={"brief": "test"}
        )
        ctx = JobContext(job_id="abc", prompt="test")
        ctx.agent_results[AgentName.DIRECTOR] = result
        json_str = ctx.model_dump_json()
        restored = JobContext.model_validate_json(json_str)
        assert AgentName.DIRECTOR in restored.agent_results
        assert restored.agent_results[AgentName.DIRECTOR].success is True


class TestJobContextOperations:
    def test_context_agent_completion_by_key(self):
        ctx = JobContext(job_id="abc", prompt="test")
        assert AgentName.DIRECTOR not in ctx.agent_results
        ctx.agent_results[AgentName.DIRECTOR] = AgentResult(
            agent_name=AgentName.DIRECTOR, success=True
        )
        assert AgentName.DIRECTOR in ctx.agent_results

    def test_context_status_transitions(self):
        ctx = JobContext(job_id="abc", prompt="test")
        assert ctx.status == JobStatus.PENDING
        ctx.status = JobStatus.RUNNING
        assert ctx.status == JobStatus.RUNNING
        ctx.status = JobStatus.COMPLETED
        assert ctx.status == JobStatus.COMPLETED
        ctx.status = JobStatus.FAILED
        assert ctx.status == JobStatus.FAILED

    def test_context_updated_at_tracks_changes(self):
        ctx = JobContext(job_id="abc", prompt="test")
        original_updated = ctx.updated_at
        # Model does NOT auto-update updated_at on field changes
        ctx.status = JobStatus.RUNNING
        assert ctx.updated_at == original_updated
        # Caller must manually update it
        ctx.updated_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert ctx.updated_at != original_updated
