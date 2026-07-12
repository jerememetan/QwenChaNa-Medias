import pytest
from unittest.mock import MagicMock

from agents.director import DirectorAgent
from models.enums import AgentName
from models.workflow_state import WorkflowState
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from tools.llm import LLMService


def _make_context(prompt: str = "Create a 30-second explainer about AI") -> WorkflowState:
    return WorkflowState(job_id="test-job", prompt=prompt)


def _mock_llm_service(response: str) -> MagicMock:
    mock = MagicMock(spec=LLMService)
    mock.generate.return_value = response
    return mock


class TestDirectorAgent:
    def test_name_is_director(self):
        agent = DirectorAgent(llm_service=_mock_llm_service("irrelevant"))
        assert agent.name == AgentName.DIRECTOR

    def test_run_returns_workflow_state(self):
        brief_json = '{"title":"AI Explainer","prompt":"Create a 30-second explainer about AI","tone":"informative","audience":"general","duration_seconds":30.0,"summary":"A brief overview of artificial intelligence"}'
        agent = DirectorAgent(llm_service=_mock_llm_service(brief_json))
        ctx = _make_context()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_run_writes_agent_result_to_context(self):
        brief_json = '{"title":"AI Explainer","prompt":"Create a 30-second explainer about AI","tone":"informative","audience":"general","duration_seconds":30.0,"summary":"A brief overview of artificial intelligence"}'
        agent = DirectorAgent(llm_service=_mock_llm_service(brief_json))
        ctx = _make_context()
        result = agent.run(ctx)
        assert AgentName.DIRECTOR in result.agent_results
        agent_result = result.agent_results[AgentName.DIRECTOR]
        assert agent_result.success is True
        assert agent_result.agent_name == AgentName.DIRECTOR

    def test_run_stores_brief_in_output_data(self):
        brief_json = '{"title":"AI Explainer","prompt":"Create a 30-second explainer about AI","tone":"informative","audience":"general","duration_seconds":30.0,"summary":"A brief overview of artificial intelligence"}'
        agent = DirectorAgent(llm_service=_mock_llm_service(brief_json))
        ctx = _make_context()
        result = agent.run(ctx)
        output_data = result.agent_results[AgentName.DIRECTOR].output_data
        brief = CreativeBrief.model_validate(output_data)
        assert brief.title == "AI Explainer"
        assert brief.duration_seconds == 30.0

    def test_run_raises_on_invalid_llm_response(self):
        agent = DirectorAgent(llm_service=_mock_llm_service("not valid json at all"))
        ctx = _make_context()
        with pytest.raises(ValueError):
            agent.run(ctx)

    def test_run_raises_on_llm_service_error(self):
        mock_llm = MagicMock(spec=LLMService)
        mock_llm.generate.side_effect = RuntimeError("LLM API timeout")
        agent = DirectorAgent(llm_service=mock_llm)
        ctx = _make_context()
        with pytest.raises(RuntimeError, match="LLM API timeout"):
            agent.run(ctx)

    def test_prompt_includes_user_prompt(self):
        brief_json = '{"title":"AI Explainer","prompt":"Create a 30-second explainer about AI","tone":"informative","audience":"general","duration_seconds":30.0,"summary":"A brief overview of artificial intelligence"}'
        mock_llm = _mock_llm_service(brief_json)
        agent = DirectorAgent(llm_service=mock_llm)
        ctx = _make_context(prompt="My custom video prompt")
        agent.run(ctx)
        call_prompt = mock_llm.generate.call_args.args[0]
        assert "My custom video prompt" in call_prompt

    def test_run_persists_brief_json_to_storage(self):
        brief_json = '{"title":"AI Explainer","prompt":"Create a 30-second explainer about AI","tone":"informative","audience":"general","duration_seconds":30.0,"summary":"A brief overview of artificial intelligence"}'
        mock_llm = _mock_llm_service(brief_json)
        mock_storage = MagicMock()
        agent = DirectorAgent(llm_service=mock_llm, storage=mock_storage)
        ctx = _make_context()
        agent.run(ctx)
        saved_data = CreativeBrief.model_validate_json(brief_json).model_dump(mode="json")
        mock_storage.save.assert_called_once_with(
            "test-job", "director", "creative_brief.json", saved_data,
        )
