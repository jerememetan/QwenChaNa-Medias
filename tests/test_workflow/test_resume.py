"""Layer 7: Resume tests — verify context loading, agent skipping, failure recovery."""

import pytest

from agents.base import BaseAgent
from models.agent_result import AgentResult
from models.enums import AgentName, JobStatus
from models.workflow_state import WorkflowState
from storage.local import LocalStorage
from workflow.resume import resume_job


class StubAgent(BaseAgent):
    """Concrete agent that records calls and optionally fails."""

    name: AgentName = AgentName.DIRECTOR

    def __init__(
        self,
        agent_name: AgentName,
        should_fail: bool = False,
        call_order: list | None = None,
    ) -> None:
        self.name = agent_name
        self.should_fail = should_fail
        self.call_order = call_order
        super().__init__()

    def run(self, context: WorkflowState) -> WorkflowState:
        if self.call_order is not None:
            self.call_order.append(self.name)
        if self.should_fail:
            raise RuntimeError(f"Agent {self.name} failed")
        context.agent_results[self.name] = AgentResult(
            agent_name=self.name, success=True, output_data={"ran": True}
        )
        return context


ALL_AGENTS = [
    AgentName.DIRECTOR,
    AgentName.RESEARCH,
    AgentName.SCRIPT,
    AgentName.STORYBOARD,
    AgentName.VIDEO,
    AgentName.VOICE,
    AgentName.EDITOR,
]


def _make_stub_agents(
    names: list[AgentName],
    should_fail: AgentName | None = None,
    call_order: list | None = None,
) -> list[StubAgent]:
    return [
        StubAgent(n, should_fail=(n == should_fail), call_order=call_order)
        for n in names
    ]


def _save_context(storage: LocalStorage, job_id: str, context: WorkflowState) -> None:
    """Persist context to storage for resume tests."""
    data = context.model_dump(mode="json")
    storage.save(job_id, "pipeline", "context.json", data)


class TestResumeLoadsContext:
    def test_resume_loads_context_from_storage(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        ctx = WorkflowState(job_id="load-test", prompt="test")
        ctx.agent_results[AgentName.DIRECTOR] = AgentResult(
            agent_name=AgentName.DIRECTOR, success=True
        )
        _save_context(storage, "load-test", ctx)

        agents = _make_stub_agents(ALL_AGENTS)
        result = resume_job("load-test", agents, storage)
        assert result.job_id == "load-test"
        assert result.prompt == "test"


class TestResumeSkipsCompleted:
    def test_resume_skips_completed_agents(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        ctx = WorkflowState(job_id="skip-test", prompt="test")
        ctx.agent_results[AgentName.DIRECTOR] = AgentResult(
            agent_name=AgentName.DIRECTOR, success=True
        )
        ctx.agent_results[AgentName.RESEARCH] = AgentResult(
            agent_name=AgentName.RESEARCH, success=True
        )
        _save_context(storage, "skip-test", ctx)

        call_order: list = []
        agents = _make_stub_agents(ALL_AGENTS, call_order=call_order)
        result = resume_job("skip-test", agents, storage)
        # DIRECTOR and RESEARCH already complete — should not be called
        assert AgentName.DIRECTOR not in call_order
        assert AgentName.RESEARCH not in call_order
        # Remaining agents should run
        assert AgentName.SCRIPT in call_order


class TestResumeFromFailedAgent:
    def test_resume_runs_from_failed_agent(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        ctx = WorkflowState(job_id="fail-resume", prompt="test")
        ctx.agent_results[AgentName.DIRECTOR] = AgentResult(
            agent_name=AgentName.DIRECTOR, success=True
        )
        ctx.status = JobStatus.FAILED
        ctx.failed_agent = AgentName.RESEARCH
        ctx.error = "Agent research failed"
        _save_context(storage, "fail-resume", ctx)

        call_order: list = []
        agents = _make_stub_agents(ALL_AGENTS, call_order=call_order)
        result = resume_job("fail-resume", agents, storage)
        # DIRECTOR is complete — skipped
        assert AgentName.DIRECTOR not in call_order
        # RESEARCH was failed (not in agent_results) — runs again
        assert AgentName.RESEARCH in call_order
        # STORYBOARD runs after RESEARCH
        assert AgentName.STORYBOARD in call_order


class TestResumeMissingContext:
    def test_resume_raises_for_missing_context(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        agents = _make_stub_agents(ALL_AGENTS)
        with pytest.raises(FileNotFoundError, match="context.json"):
            resume_job("nonexistent", agents, storage)


class TestResumeStatusUpdates:
    def test_resume_updates_job_status(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        ctx = WorkflowState(job_id="status-resume", prompt="test")
        ctx.agent_results[AgentName.DIRECTOR] = AgentResult(
            agent_name=AgentName.DIRECTOR, success=True
        )
        ctx.status = JobStatus.FAILED
        ctx.failed_agent = AgentName.RESEARCH
        ctx.error = "Agent research failed"
        _save_context(storage, "status-resume", ctx)

        agents = _make_stub_agents(ALL_AGENTS)
        result = resume_job("status-resume", agents, storage)
        assert result.status == JobStatus.COMPLETED


class TestResumeClearsFailure:
    def test_resume_clears_previous_failure(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        ctx = WorkflowState(job_id="clear-fail", prompt="test")
        ctx.status = JobStatus.FAILED
        ctx.failed_agent = AgentName.RESEARCH
        ctx.error = "Agent research failed"
        _save_context(storage, "clear-fail", ctx)

        agents = _make_stub_agents(ALL_AGENTS)
        result = resume_job("clear-fail", agents, storage)
        assert result.failed_agent is None
        assert result.error is None


class TestResumePersistence:
    def test_resume_persists_context_for_new_agents(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        ctx = WorkflowState(job_id="persist-resume", prompt="test")
        ctx.agent_results[AgentName.DIRECTOR] = AgentResult(
            agent_name=AgentName.DIRECTOR, success=True
        )
        _save_context(storage, "persist-resume", ctx)

        agents = _make_stub_agents(ALL_AGENTS)
        resume_job("persist-resume", agents, storage)
        # Context should be persisted after resume
        loaded = storage.load("persist-resume", "pipeline", "context.json")
        assert loaded is not None
        assert loaded["status"] == "completed"
