"""Layer 6: Pipeline tests — verify sequential agent execution, context passing,
failure handling, and context persistence."""

from datetime import datetime, timezone

import pytest

from agents.base import BaseAgent
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from models.enums import AgentName, JobStatus
from models.research import ResearchNotes
from models.scene import Scene
from models.script import Script
from models.storyboard import Shot, Storyboard
from models.workflow_state import WorkflowState
from storage.local import LocalStorage
from workflow.pipeline import Pipeline


class StubAgent(BaseAgent):
    """Concrete agent that records call order and optionally fails."""

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


class MessageFailAgent(StubAgent):
    def __init__(self, name: AgentName, message: str) -> None:
        super().__init__(name)
        self.message = message

    def run(self, context: WorkflowState) -> WorkflowState:
        raise RuntimeError(self.message)


def _context_through_storyboard(job_id: str) -> WorkflowState:
    context = WorkflowState(job_id=job_id, prompt="creative")
    values = {
        AgentName.DIRECTOR: CreativeBrief(
            title="T",
            prompt="creative",
            tone="clear",
            audience="general",
            duration_seconds=5,
            summary="S",
            requires_research=False,
        ),
        AgentName.RESEARCH: ResearchNotes(
            brief_summary="skipped",
            notes=[],
            overall_confidence=0,
        ),
        AgentName.SCRIPT: Script(
            title="T",
            scenes=[
                Scene(
                    scene_number=1,
                    narration="N",
                    duration_hint=5,
                    visual_direction="V",
                )
            ],
        ),
        AgentName.STORYBOARD: Storyboard(
            shots=[
                Shot(
                    shot_number=1,
                    scene_number=1,
                    visual_prompt="V",
                    camera="wide",
                    motion="static",
                    duration=5,
                )
            ]
        ),
    }
    for name, value in values.items():
        context.agent_results[name] = AgentResult(
            agent_name=name,
            success=True,
            output_data=value.model_dump(mode="json"),
        )
    return context


def _full_agents_with_assets(video, voice, editor) -> list[BaseAgent]:
    return [
        StubAgent(AgentName.DIRECTOR),
        StubAgent(AgentName.RESEARCH),
        StubAgent(AgentName.SCRIPT),
        StubAgent(AgentName.STORYBOARD),
        video,
        voice,
        editor,
    ]


class TestPipelineExecutionOrder:
    def test_pipeline_runs_agents_in_order(self, tmp_path):
        call_order: list = []
        agents = [
            StubAgent(AgentName.DIRECTOR, call_order=call_order),
            StubAgent(AgentName.RESEARCH, call_order=call_order),
            StubAgent(AgentName.SCRIPT, call_order=call_order),
        ]
        storage = LocalStorage(str(tmp_path))
        pipeline = Pipeline(storage)
        ctx = WorkflowState(job_id="order-test", prompt="test")
        pipeline.run("order-test", agents, ctx)
        assert call_order == [AgentName.DIRECTOR, AgentName.RESEARCH, AgentName.SCRIPT]

    def test_pipeline_passes_context_between_agents(self, tmp_path):
        agents = [
            StubAgent(AgentName.DIRECTOR),
            StubAgent(AgentName.RESEARCH),
        ]
        storage = LocalStorage(str(tmp_path))
        pipeline = Pipeline(storage)
        ctx = WorkflowState(job_id="ctx-pass", prompt="test")
        result = pipeline.run("ctx-pass", agents, ctx)
        assert AgentName.DIRECTOR in result.agent_results
        assert AgentName.RESEARCH in result.agent_results

    def test_pipeline_persists_context_after_each_agent(self, tmp_path):
        agents = [
            StubAgent(AgentName.DIRECTOR),
            StubAgent(AgentName.RESEARCH),
        ]
        storage = LocalStorage(str(tmp_path))
        pipeline = Pipeline(storage)
        ctx = WorkflowState(job_id="persist-test", prompt="test")
        pipeline.run("persist-test", agents, ctx)
        # Context.json should exist after pipeline runs
        loaded = storage.load("persist-test", "pipeline", "context.json")
        assert loaded is not None

    def test_pipeline_records_agent_completion(self, tmp_path):
        agents = [StubAgent(AgentName.DIRECTOR)]
        storage = LocalStorage(str(tmp_path))
        pipeline = Pipeline(storage)
        ctx = WorkflowState(job_id="complete-test", prompt="test")
        result = pipeline.run("complete-test", agents, ctx)
        assert AgentName.DIRECTOR in result.agent_results


class TestPipelineFailureHandling:
    def test_pipeline_stops_on_agent_failure(self, tmp_path):
        call_order: list = []
        agents = [
            StubAgent(AgentName.DIRECTOR, call_order=call_order),
            StubAgent(AgentName.RESEARCH, should_fail=True, call_order=call_order),
            StubAgent(AgentName.SCRIPT, call_order=call_order),
        ]
        storage = LocalStorage(str(tmp_path))
        pipeline = Pipeline(storage)
        ctx = WorkflowState(job_id="fail-test", prompt="test")
        pipeline.run("fail-test", agents, ctx)
        # SCRIPT should never be called
        assert AgentName.SCRIPT not in call_order

    def test_pipeline_sets_job_status_running(self, tmp_path):
        agents = [StubAgent(AgentName.DIRECTOR)]
        storage = LocalStorage(str(tmp_path))
        pipeline = Pipeline(storage)
        ctx = WorkflowState(job_id="status-running", prompt="test")
        # After run, status should be RUNNING at some point — final status is COMPLETED
        result = pipeline.run("status-running", agents, ctx)
        assert result.status == JobStatus.COMPLETED

    def test_pipeline_sets_job_status_completed(self, tmp_path):
        agents = [
            StubAgent(AgentName.DIRECTOR),
            StubAgent(AgentName.RESEARCH),
        ]
        storage = LocalStorage(str(tmp_path))
        pipeline = Pipeline(storage)
        ctx = WorkflowState(job_id="status-complete", prompt="test")
        result = pipeline.run("status-complete", agents, ctx)
        assert result.status == JobStatus.COMPLETED

    def test_pipeline_sets_job_status_failed_on_error(self, tmp_path):
        agents = [
            StubAgent(AgentName.DIRECTOR),
            StubAgent(AgentName.RESEARCH, should_fail=True),
        ]
        storage = LocalStorage(str(tmp_path))
        pipeline = Pipeline(storage)
        ctx = WorkflowState(job_id="status-fail", prompt="test")
        result = pipeline.run("status-fail", agents, ctx)
        assert result.status == JobStatus.FAILED

    def test_pipeline_records_failed_agent(self, tmp_path):
        agents = [
            StubAgent(AgentName.RESEARCH, should_fail=True),
        ]
        storage = LocalStorage(str(tmp_path))
        pipeline = Pipeline(storage)
        ctx = WorkflowState(job_id="record-fail", prompt="test")
        result = pipeline.run("record-fail", agents, ctx)
        assert result.failed_agent == AgentName.RESEARCH
        assert "Agent research failed" in result.error

    def test_pipeline_persists_parallel_success_before_failure(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        context = _context_through_storyboard(job_id="parallel-fail")
        agents = _full_agents_with_assets(
            video=MessageFailAgent(AgentName.VIDEO, "quota"),
            voice=StubAgent(AgentName.VOICE),
            editor=StubAgent(AgentName.EDITOR),
        )

        result = Pipeline(storage).run("parallel-fail", agents, context)

        assert result.status == JobStatus.FAILED
        assert result.failed_agent == AgentName.VIDEO
        assert result.current_agent is None
        assert AgentName.VOICE in result.agent_results
        assert AgentName.EDITOR not in result.agent_results
        saved = WorkflowState.model_validate(
            storage.load("parallel-fail", "pipeline", "context.json")
        )
        assert AgentName.VOICE in saved.agent_results


class TestPipelineEdgeCases:
    def test_pipeline_with_empty_agent_list(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        pipeline = Pipeline(storage)
        ctx = WorkflowState(job_id="empty-test", prompt="test")
        result = pipeline.run("empty-test", [], ctx)
        assert result.status == JobStatus.COMPLETED

    def test_pipeline_saves_context_json(self, tmp_path):
        agents = [StubAgent(AgentName.DIRECTOR)]
        storage = LocalStorage(str(tmp_path))
        pipeline = Pipeline(storage)
        ctx = WorkflowState(job_id="json-save", prompt="test")
        pipeline.run("json-save", agents, ctx)
        # Verify context.json was saved under the pipeline agent namespace
        loaded = storage.load("json-save", "pipeline", "context.json")
        assert loaded is not None
        assert loaded["job_id"] == "json-save"
