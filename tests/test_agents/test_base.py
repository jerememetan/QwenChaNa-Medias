import pytest

from models.enums import AgentName
from models.workflow_state import WorkflowState

from agents.base import BaseAgent


class StubAgent(BaseAgent):
    """Concrete agent for testing — succeeds by default."""

    name: AgentName = AgentName.DIRECTOR

    def run(self, context: WorkflowState) -> WorkflowState:
        return context


class FailingAgent(BaseAgent):
    """Concrete agent that raises on run."""

    name: AgentName = AgentName.SCRIPT

    def run(self, context: WorkflowState) -> WorkflowState:
        raise RuntimeError("LLM timeout")


class NoNameAgent(BaseAgent):
    """Subclass without a name attribute."""

    def run(self, context: WorkflowState) -> WorkflowState:
        return context


class NoRunAgent(BaseAgent):
    """Subclass without a run method."""

    name: AgentName = AgentName.RESEARCH


class TestBaseAgent:
    def test_base_agent_is_abstract(self):
        with pytest.raises(TypeError):
            BaseAgent()

    def test_base_agent_requires_name(self):
        with pytest.raises(TypeError):
            NoNameAgent()

    def test_base_agent_requires_run_method(self):
        with pytest.raises(TypeError):
            NoRunAgent()

    def test_concrete_agent_run_receives_context(self):
        ctx = WorkflowState(job_id="abc", prompt="test")
        agent = StubAgent()
        result = agent.run(ctx)
        assert result.job_id == "abc"

    def test_concrete_agent_run_returns_context(self):
        ctx = WorkflowState(job_id="abc", prompt="test")
        agent = StubAgent()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_agent_name_matches_enum(self):
        agent = StubAgent()
        assert agent.name == AgentName.DIRECTOR
        assert agent.name in set(AgentName)
