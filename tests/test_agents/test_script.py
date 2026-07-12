import pytest
from unittest.mock import MagicMock

from agents.script import ScriptAgent
from models.enums import AgentName
from models.workflow_state import WorkflowState
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from models.research import ResearchNotes, ResearchNote
from models.script import Script
from tools.llm import LLMService
from storage.base import StorageBackend


def _make_context_with_upstream() -> WorkflowState:
    ctx = WorkflowState(job_id="test-job", prompt="Create a 30s explainer about AI")
    brief = CreativeBrief(
        title="AI Explainer",
        prompt="Create a 30s explainer about AI",
        tone="informative",
        audience="general",
        duration_seconds=30.0,
        summary="A brief overview of AI",
    )
    ctx.agent_results[AgentName.DIRECTOR] = AgentResult(
        agent_name=AgentName.DIRECTOR, success=True, output_data=brief.model_dump(mode="json"),
    )
    notes = ResearchNotes(
        brief_summary="AI overview",
        notes=[ResearchNote(topic="AI definition", content="AI simulates human intelligence")],
        overall_confidence=0.7,
    )
    ctx.agent_results[AgentName.RESEARCH] = AgentResult(
        agent_name=AgentName.RESEARCH, success=True, output_data=notes.model_dump(mode="json"),
    )
    return ctx


def _mock_llm_service(response: str) -> MagicMock:
    mock = MagicMock(spec=LLMService)
    mock.generate.return_value = response
    return mock


class TestScriptAgent:
    def test_name_is_script(self):
        agent = ScriptAgent(llm_service=_mock_llm_service("irrelevant"))
        assert agent.name == AgentName.SCRIPT

    def test_run_returns_workflow_state(self):
        script_json = '{"title":"AI Explainer","scenes":[{"scene_number":1,"narration":"AI is transforming the world","duration_hint":15.0,"visual_direction":"Show AI systems in action"}]}'
        agent = ScriptAgent(llm_service=_mock_llm_service(script_json))
        ctx = _make_context_with_upstream()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_run_writes_agent_result(self):
        script_json = '{"title":"AI Explainer","scenes":[{"scene_number":1,"narration":"AI is transforming the world","duration_hint":15.0,"visual_direction":"Show AI systems in action"}]}'
        agent = ScriptAgent(llm_service=_mock_llm_service(script_json))
        ctx = _make_context_with_upstream()
        result = agent.run(ctx)
        assert AgentName.SCRIPT in result.agent_results
        assert result.agent_results[AgentName.SCRIPT].success is True

    def test_run_stores_script_in_output_data(self):
        script_json = '{"title":"AI Explainer","scenes":[{"scene_number":1,"narration":"AI is transforming the world","duration_hint":15.0,"visual_direction":"Show AI systems in action","mood":"inspiring"}]}'
        agent = ScriptAgent(llm_service=_mock_llm_service(script_json))
        ctx = _make_context_with_upstream()
        result = agent.run(ctx)
        script = Script.model_validate(result.agent_results[AgentName.SCRIPT].output_data)
        assert script.title == "AI Explainer"
        assert len(script.scenes) == 1
        assert script.scenes[0].narration == "AI is transforming the world"

    def test_run_raises_when_director_missing(self):
        agent = ScriptAgent(llm_service=_mock_llm_service("irrelevant"))
        ctx = WorkflowState(job_id="test-job", prompt="test")
        with pytest.raises(ValueError, match="Director"):
            agent.run(ctx)

    def test_run_raises_when_research_missing(self):
        agent = ScriptAgent(llm_service=_mock_llm_service("irrelevant"))
        ctx = WorkflowState(job_id="test-job", prompt="test")
        brief = CreativeBrief(title="T", prompt="P", tone="t", audience="a", duration_seconds=10.0, summary="s")
        ctx.agent_results[AgentName.DIRECTOR] = AgentResult(
            agent_name=AgentName.DIRECTOR, success=True, output_data=brief.model_dump(mode="json"),
        )
        with pytest.raises(ValueError, match="Research"):
            agent.run(ctx)

    def test_run_raises_on_invalid_llm_response(self):
        agent = ScriptAgent(llm_service=_mock_llm_service("not json"))
        ctx = _make_context_with_upstream()
        with pytest.raises(ValueError):
            agent.run(ctx)

    def test_run_persists_to_storage(self):
        script_json = '{"title":"AI Explainer","scenes":[{"scene_number":1,"narration":"AI is transforming the world","duration_hint":15.0,"visual_direction":"Show AI systems in action"}]}'
        mock_llm = _mock_llm_service(script_json)
        mock_storage = MagicMock(spec=StorageBackend)
        agent = ScriptAgent(llm_service=mock_llm, storage=mock_storage)
        ctx = _make_context_with_upstream()
        agent.run(ctx)
        saved_data = Script.model_validate_json(script_json).model_dump(mode="json")
        mock_storage.save.assert_called_once_with(
            "test-job", "script", "script.json", saved_data,
        )
