import pytest
from unittest.mock import MagicMock

from agents.research import ResearchAgent
from models.enums import AgentName
from models.workflow_state import WorkflowState
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from models.research import ResearchNotes
from tools.llm import LLMService
from storage.base import StorageBackend


def _make_context_with_brief() -> WorkflowState:
    ctx = WorkflowState(job_id="test-job", prompt="Create a 30s explainer about AI")
    brief = CreativeBrief(
        title="AI Explainer",
        prompt="Create a 30s explainer about AI",
        tone="informative",
        audience="general",
        duration_seconds=30.0,
        summary="A brief overview of artificial intelligence",
    )
    ctx.agent_results[AgentName.DIRECTOR] = AgentResult(
        agent_name=AgentName.DIRECTOR,
        success=True,
        output_data=brief.model_dump(mode="json"),
    )
    return ctx


def _mock_llm_service(response: str) -> MagicMock:
    mock = MagicMock(spec=LLMService)
    mock.generate.return_value = response
    return mock


class TestResearchAgent:
    def test_name_is_research(self):
        agent = ResearchAgent(llm_service=_mock_llm_service("irrelevant"))
        assert agent.name == AgentName.RESEARCH

    def test_run_returns_workflow_state(self):
        research_json = '{"brief_summary":"AI overview","notes":[{"topic":"AI definition","content":"Artificial intelligence is...","source":"Wikipedia","verified":true}],"overall_confidence":0.8}'
        agent = ResearchAgent(llm_service=_mock_llm_service(research_json))
        ctx = _make_context_with_brief()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_run_writes_agent_result(self):
        research_json = '{"brief_summary":"AI overview","notes":[{"topic":"AI definition","content":"Artificial intelligence is..."}],"overall_confidence":0.7}'
        agent = ResearchAgent(llm_service=_mock_llm_service(research_json))
        ctx = _make_context_with_brief()
        result = agent.run(ctx)
        assert AgentName.RESEARCH in result.agent_results
        assert result.agent_results[AgentName.RESEARCH].success is True

    def test_run_stores_research_in_output_data(self):
        research_json = '{"brief_summary":"AI overview","notes":[{"topic":"AI definition","content":"Artificial intelligence is machine simulation of human intelligence","source":"Stanford","verified":true}],"overall_confidence":0.85}'
        agent = ResearchAgent(llm_service=_mock_llm_service(research_json))
        ctx = _make_context_with_brief()
        result = agent.run(ctx)
        output_data = result.agent_results[AgentName.RESEARCH].output_data
        notes = ResearchNotes.model_validate(output_data)
        assert notes.brief_summary == "AI overview"
        assert len(notes.notes) == 1

    def test_run_raises_when_director_output_missing(self):
        agent = ResearchAgent(llm_service=_mock_llm_service("irrelevant"))
        ctx = WorkflowState(job_id="test-job", prompt="test")
        with pytest.raises(ValueError, match="Director"):
            agent.run(ctx)

    def test_run_raises_on_invalid_llm_response(self):
        agent = ResearchAgent(llm_service=_mock_llm_service("garbage response"))
        ctx = _make_context_with_brief()
        with pytest.raises(ValueError):
            agent.run(ctx)

    def test_run_persists_to_storage(self):
        research_json = '{"brief_summary":"AI overview","notes":[],"overall_confidence":0.5}'
        mock_llm = _mock_llm_service(research_json)
        mock_storage = MagicMock(spec=StorageBackend)
        agent = ResearchAgent(llm_service=mock_llm, storage=mock_storage)
        ctx = _make_context_with_brief()
        agent.run(ctx)
        saved_data = ResearchNotes.model_validate_json(research_json).model_dump(mode="json")
        mock_storage.save.assert_called_once_with(
            "test-job", "research", "research_notes.json", saved_data,
        )
