import pytest
from unittest.mock import MagicMock

from agents.storyboard import StoryboardAgent
from models.enums import AgentName
from models.workflow_state import WorkflowState
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from models.research import ResearchNotes
from models.script import Script
from models.scene import Scene
from models.storyboard import Storyboard
from tools.llm import LLMService
from storage.base import StorageBackend


def _make_context_with_upstream(
    requested_shot_count: int | None = None,
) -> WorkflowState:
    ctx = WorkflowState(job_id="test-job", prompt="Create a 30s explainer about AI")
    brief = CreativeBrief(
        title="AI Explainer", prompt="Create a 30s explainer about AI",
        tone="informative", audience="general", duration_seconds=30.0, summary="AI overview",
        requested_shot_count=requested_shot_count,
    )
    ctx.agent_results[AgentName.DIRECTOR] = AgentResult(
        agent_name=AgentName.DIRECTOR, success=True, output_data=brief.model_dump(mode="json"),
    )
    notes = ResearchNotes(brief_summary="AI overview", notes=[], overall_confidence=0.7)
    ctx.agent_results[AgentName.RESEARCH] = AgentResult(
        agent_name=AgentName.RESEARCH, success=True, output_data=notes.model_dump(mode="json"),
    )
    script = Script(
        title="AI Explainer",
        scenes=[Scene(scene_number=1, narration="AI is transforming the world", duration_hint=15.0, visual_direction="Show AI systems")],
    )
    ctx.agent_results[AgentName.SCRIPT] = AgentResult(
        agent_name=AgentName.SCRIPT, success=True, output_data=script.model_dump(mode="json"),
    )
    return ctx


def _mock_llm_service(response: str) -> MagicMock:
    mock = MagicMock(spec=LLMService)
    mock.generate.return_value = response
    return mock


class TestStoryboardAgent:
    def test_name_is_storyboard(self):
        agent = StoryboardAgent(llm_service=_mock_llm_service("irrelevant"))
        assert agent.name == AgentName.STORYBOARD

    def test_run_returns_workflow_state(self):
        sb_json = '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"A futuristic AI lab","camera":"medium shot","motion":"slow pan","duration":15.0}]}'
        agent = StoryboardAgent(llm_service=_mock_llm_service(sb_json))
        ctx = _make_context_with_upstream()
        result = agent.run(ctx)
        assert isinstance(result, WorkflowState)

    def test_run_writes_agent_result(self):
        sb_json = '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"A futuristic AI lab","camera":"medium shot","motion":"slow pan","duration":15.0}]}'
        agent = StoryboardAgent(llm_service=_mock_llm_service(sb_json))
        ctx = _make_context_with_upstream()
        result = agent.run(ctx)
        assert AgentName.STORYBOARD in result.agent_results
        assert result.agent_results[AgentName.STORYBOARD].success is True

    def test_run_stores_storyboard_in_output_data(self):
        sb_json = '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"A futuristic AI lab","camera":"medium shot","motion":"slow pan","duration":15.0,"mood":"inspiring"}]}'
        agent = StoryboardAgent(llm_service=_mock_llm_service(sb_json))
        ctx = _make_context_with_upstream()
        result = agent.run(ctx)
        sb = Storyboard.model_validate(result.agent_results[AgentName.STORYBOARD].output_data)
        assert len(sb.shots) == 1
        assert sb.shots[0].visual_prompt == "A futuristic AI lab"

    def test_run_requires_director_output(self):
        ctx = _make_context_with_upstream()
        del ctx.agent_results[AgentName.DIRECTOR]

        with pytest.raises(ValueError, match="Director"):
            StoryboardAgent(_mock_llm_service("irrelevant")).run(ctx)

    def test_prompt_requests_renderable_voxel_geometry(self):
        llm = _mock_llm_service(
            '{"shots":[{"shot_number":1,"scene_number":1,'
            '"visual_prompt":"A cubic block","camera":"wide",'
            '"motion":"static","duration":15}]}'
        )

        StoryboardAgent(llm).run(_make_context_with_upstream())

        prompt = llm.generate.call_args.args[0]
        assert "flat pixel textures" in prompt
        assert "no photorealistic foliage" in prompt
        assert "sound instructions" in prompt

    def test_shot_count_mismatch_gets_one_correction(self):
        two_shots = (
            '{"shots":['
            '{"shot_number":1,"scene_number":1,"visual_prompt":"A",'
            '"camera":"wide","motion":"static","duration":7.5},'
            '{"shot_number":2,"scene_number":1,"visual_prompt":"B",'
            '"camera":"wide","motion":"static","duration":7.5}]}'
        )
        one_shot = (
            '{"shots":[{"shot_number":1,"scene_number":1,'
            '"visual_prompt":"A cubic block","camera":"wide",'
            '"motion":"static","duration":15}]}'
        )
        llm = MagicMock(spec=LLMService)
        llm.generate.side_effect = [two_shots, one_shot]

        result = StoryboardAgent(llm).run(
            _make_context_with_upstream(requested_shot_count=1)
        )

        assert llm.generate.call_count == 2
        assert len(
            result.agent_results[AgentName.STORYBOARD].output_data["shots"]
        ) == 1

    def test_second_shot_count_mismatch_fails(self):
        two_shots = (
            '{"shots":['
            '{"shot_number":1,"scene_number":1,"visual_prompt":"A",'
            '"camera":"wide","motion":"static","duration":7.5},'
            '{"shot_number":2,"scene_number":1,"visual_prompt":"B",'
            '"camera":"wide","motion":"static","duration":7.5}]}'
        )
        llm = MagicMock(spec=LLMService)
        llm.generate.side_effect = [two_shots, two_shots]

        with pytest.raises(ValueError, match="exactly 1 shot"):
            StoryboardAgent(llm).run(
                _make_context_with_upstream(requested_shot_count=1)
            )

    def test_bad_scene_duration_gets_one_correction(self):
        short = (
            '{"shots":[{"shot_number":1,"scene_number":1,'
            '"visual_prompt":"A","camera":"wide","motion":"static",'
            '"duration":5}]}'
        )
        corrected = (
            '{"shots":[{"shot_number":1,"scene_number":1,'
            '"visual_prompt":"A","camera":"wide","motion":"static",'
            '"duration":15}]}'
        )
        llm = MagicMock(spec=LLMService)
        llm.generate.side_effect = [short, corrected]

        StoryboardAgent(llm).run(_make_context_with_upstream())

        assert llm.generate.call_count == 2

    def test_unknown_script_scene_fails_after_correction(self):
        unknown = (
            '{"shots":[{"shot_number":1,"scene_number":2,'
            '"visual_prompt":"A","camera":"wide","motion":"static",'
            '"duration":15}]}'
        )
        llm = MagicMock(spec=LLMService)
        llm.generate.side_effect = [unknown, unknown]

        with pytest.raises(ValueError, match="unknown script scene 2"):
            StoryboardAgent(llm).run(_make_context_with_upstream())

    def test_run_raises_when_script_missing(self):
        agent = StoryboardAgent(llm_service=_mock_llm_service("irrelevant"))
        ctx = WorkflowState(job_id="test-job", prompt="test")
        with pytest.raises(ValueError, match="Script"):
            agent.run(ctx)

    def test_run_raises_on_invalid_llm_response(self):
        agent = StoryboardAgent(llm_service=_mock_llm_service("not json"))
        ctx = _make_context_with_upstream()
        with pytest.raises(ValueError):
            agent.run(ctx)

    def test_run_persists_to_storage(self):
        sb_json = '{"shots":[{"shot_number":1,"scene_number":1,"visual_prompt":"A futuristic AI lab","camera":"medium shot","motion":"slow pan","duration":15.0}]}'
        mock_llm = _mock_llm_service(sb_json)
        mock_storage = MagicMock(spec=StorageBackend)
        agent = StoryboardAgent(llm_service=mock_llm, storage=mock_storage)
        ctx = _make_context_with_upstream()
        agent.run(ctx)
        saved_data = Storyboard.model_validate_json(sb_json).model_dump(mode="json")
        mock_storage.save.assert_called_once_with(
            "test-job", "storyboard", "storyboard.json", saved_data,
        )
