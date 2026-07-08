import pytest
from pydantic import ValidationError

from models.agent_result import AgentResult, ArtifactRef
from models.brief import CreativeBrief
from models.enums import AgentName
from models.research import ResearchNote, ResearchNotes
from models.scene import Scene
from models.script import Script
from models.storyboard import Shot, Storyboard
from models.workflow_state import WorkflowState


class TestCreativeBrief:
    def test_creative_brief_required_fields(self):
        brief = CreativeBrief(
            title="Test Video",
            prompt="A short video",
            tone="informative",
            audience="general",
            duration_seconds=30.0,
            summary="A brief summary",
        )
        assert brief.title == "Test Video"
        assert brief.duration_seconds == 30.0

    def test_creative_brief_rejects_negative_duration(self):
        with pytest.raises(ValidationError):
            CreativeBrief(
                title="Test",
                prompt="test",
                tone="neutral",
                audience="all",
                duration_seconds=-1.0,
                summary="test",
            )

    def test_creative_brief_defaults(self):
        brief = CreativeBrief(
            title="Test",
            prompt="test",
            tone="neutral",
            audience="all",
            duration_seconds=10.0,
            summary="test",
        )
        assert brief.aspect_ratio == "16:9"
        assert brief.style_keywords == []


class TestScene:
    def test_scene_required_fields(self):
        scene = Scene(
            scene_number=1,
            narration="Opening scene",
            duration_hint=5.0,
            visual_direction="Pan left",
        )
        assert scene.scene_number == 1
        assert scene.mood is None

    def test_scene_rejects_scene_number_zero(self):
        with pytest.raises(ValidationError):
            Scene(
                scene_number=0,
                narration="test",
                duration_hint=5.0,
                visual_direction="test",
            )


class TestScript:
    def test_script_requires_at_least_one_scene(self):
        with pytest.raises(ValidationError):
            Script(title="Empty", scenes=[])

    def test_script_scene_ordering(self):
        s1 = Scene(scene_number=1, narration="A", duration_hint=5.0, visual_direction="X")
        s2 = Scene(scene_number=2, narration="B", duration_hint=5.0, visual_direction="Y")
        script = Script(title="Test", scenes=[s1, s2])
        assert script.scenes[0].scene_number == 1
        assert script.scenes[1].scene_number == 2


class TestShotAndStoryboard:
    def test_shot_required_fields(self):
        shot = Shot(
            shot_number=1,
            scene_number=1,
            visual_prompt="A sunny beach",
            camera="wide",
            motion="pan left",
            duration=3.0,
        )
        assert shot.shot_number == 1
        assert shot.mood is None

    def test_storyboard_requires_at_least_one_shot(self):
        with pytest.raises(ValidationError):
            Storyboard(shots=[])


class TestResearch:
    def test_research_note_required_fields(self):
        note = ResearchNote(topic="AI trends", content="Growth in LLM usage")
        assert note.topic == "AI trends"
        assert note.source is None
        assert note.verified is False

    def test_research_notes_confidence_range(self):
        with pytest.raises(ValidationError):
            ResearchNotes(brief_summary="test", overall_confidence=1.5)


class TestAgentResult:
    def test_agent_result_success(self):
        result = AgentResult(agent_name=AgentName.DIRECTOR, success=True)
        assert result.success is True
        assert result.output_data == {}
        assert result.artifacts == []
        assert result.error is None

    def test_agent_result_failure(self):
        result = AgentResult(agent_name=AgentName.SCRIPT, success=False, error="LLM timeout")
        assert result.success is False
        assert result.error == "LLM timeout"

    def test_artifact_ref_required_fields(self):
        ref = ArtifactRef(
            agent_name=AgentName.DIRECTOR,
            filename="brief.json",
            content_type="application/json",
        )
        assert ref.size_bytes is None


class TestWorkflowState:
    def test_workflow_state_creation(self):
        state = WorkflowState(job_id="abc", prompt="test")
        assert state.status.value == "pending"
        assert state.agent_results == {}
        assert state.current_agent is None
        assert state.failed_agent is None
        assert state.error is None

    def test_workflow_state_agent_results_by_enum(self):
        result = AgentResult(agent_name=AgentName.DIRECTOR, success=True)
        state = WorkflowState(job_id="abc", prompt="test")
        state.agent_results[AgentName.DIRECTOR] = result
        assert AgentName.DIRECTOR in state.agent_results

    def test_workflow_state_json_roundtrip(self):
        result = AgentResult(agent_name=AgentName.DIRECTOR, success=True)
        state = WorkflowState(job_id="abc", prompt="test")
        state.agent_results[AgentName.DIRECTOR] = result
        json_str = state.model_dump_json()
        restored = WorkflowState.model_validate_json(json_str)
        assert restored.job_id == "abc"
        assert restored.agent_results[AgentName.DIRECTOR].success is True

    def test_workflow_state_tracks_current_agent(self):
        state = WorkflowState(job_id="abc", prompt="test")
        state.current_agent = AgentName.RESEARCH
        assert state.current_agent == AgentName.RESEARCH
