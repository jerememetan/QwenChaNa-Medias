import threading
from unittest.mock import MagicMock

import pytest

from agents.base import BaseAgent
from agents.research import ResearchAgent
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from models.enums import AgentName
from models.research import ResearchNotes
from models.scene import Scene
from models.script import Script
from models.storyboard import Shot, Storyboard
from models.workflow_state import WorkflowState
from storage.local import LocalStorage
from tools.llm import LLMService
from workflow.graph import (
    ParallelAgentError,
    build_pipeline_graph,
    workflow_to_graph_state,
)


class RecordingAgent(BaseAgent):
    def __init__(self, name: AgentName, calls: list[AgentName]) -> None:
        self.name = name
        self.calls = calls
        super().__init__()

    def run(self, context: WorkflowState) -> WorkflowState:
        self.calls.append(self.name)
        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data={"ran": True},
        )
        return context


class FailingAgent(BaseAgent):
    def __init__(self, name: AgentName, message: str) -> None:
        self.name = name
        self.message = message
        super().__init__()

    def run(self, context: WorkflowState) -> WorkflowState:
        raise RuntimeError(self.message)


class BarrierAgent(BaseAgent):
    def __init__(self, name: AgentName, barrier: threading.Barrier) -> None:
        self.name = name
        self.barrier = barrier
        super().__init__()

    def run(self, context: WorkflowState) -> WorkflowState:
        self.barrier.wait(timeout=2)
        context.agent_results[self.name] = AgentResult(
            agent_name=self.name,
            success=True,
            output_data={"ran": True},
        )
        return context


def _upstream_context(requires_research: bool) -> WorkflowState:
    context = WorkflowState(job_id="graph-job", prompt="test")
    brief = CreativeBrief(
        title="T",
        prompt="test",
        tone="clear",
        audience="general",
        duration_seconds=5,
        summary="S",
        requires_research=requires_research,
    )
    context.agent_results[AgentName.DIRECTOR] = AgentResult(
        agent_name=AgentName.DIRECTOR,
        success=True,
        output_data=brief.model_dump(mode="json"),
    )
    return context


def _full_recording_agents(storage, llm):
    calls: list[AgentName] = []
    agents = [
        RecordingAgent(AgentName.DIRECTOR, calls),
        ResearchAgent(llm, storage),
        RecordingAgent(AgentName.SCRIPT, calls),
        RecordingAgent(AgentName.STORYBOARD, calls),
        RecordingAgent(AgentName.VIDEO, calls),
        RecordingAgent(AgentName.VOICE, calls),
        RecordingAgent(AgentName.EDITOR, calls),
    ]
    return agents, calls


def _context_through_storyboard() -> WorkflowState:
    context = _upstream_context(requires_research=False)
    values = {
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


def _agents_with_assets(video, voice, editor):
    return [
        RecordingAgent(AgentName.DIRECTOR, []),
        RecordingAgent(AgentName.RESEARCH, []),
        RecordingAgent(AgentName.SCRIPT, []),
        RecordingAgent(AgentName.STORYBOARD, []),
        video,
        voice,
        editor,
    ]


def test_creative_brief_routes_through_skip_research(tmp_path):
    storage = LocalStorage(str(tmp_path))
    llm = MagicMock(spec=LLMService)
    context = _upstream_context(requires_research=False)
    agents, calls = _full_recording_agents(storage, llm)

    states = list(
        build_pipeline_graph(agents).stream(
            workflow_to_graph_state(context),
            stream_mode="values",
        )
    )

    final = states[-1]
    assert AgentName.RESEARCH in final["agent_results"]
    llm.generate.assert_not_called()
    assert AgentName.DIRECTOR not in calls
    assert AgentName.SCRIPT in calls


def test_factual_brief_calls_research_llm(tmp_path):
    storage = LocalStorage(str(tmp_path))
    llm = MagicMock(spec=LLMService)
    llm.generate.return_value = (
        '{"brief_summary":"facts","notes":[],"overall_confidence":0.0}'
    )
    context = _upstream_context(requires_research=True)
    agents, _ = _full_recording_agents(storage, llm)

    list(
        build_pipeline_graph(agents).stream(
            workflow_to_graph_state(context),
            stream_mode="values",
        )
    )

    llm.generate.assert_called_once()


def test_video_and_voice_execute_in_parallel():
    barrier = threading.Barrier(2)
    context = _context_through_storyboard()
    agents = _agents_with_assets(
        video=BarrierAgent(AgentName.VIDEO, barrier),
        voice=BarrierAgent(AgentName.VOICE, barrier),
        editor=RecordingAgent(AgentName.EDITOR, []),
    )

    final = list(
        build_pipeline_graph(agents).stream(
            workflow_to_graph_state(context),
            stream_mode="values",
        )
    )[-1]

    assert AgentName.VIDEO in final["agent_results"]
    assert AgentName.VOICE in final["agent_results"]
    assert AgentName.EDITOR in final["agent_results"]


def test_voice_success_survives_video_failure():
    context = _context_through_storyboard()
    agents = _agents_with_assets(
        video=FailingAgent(AgentName.VIDEO, "video quota"),
        voice=RecordingAgent(AgentName.VOICE, []),
        editor=RecordingAgent(AgentName.EDITOR, []),
    )
    graph = build_pipeline_graph(agents)
    results = dict(context.agent_results)

    with pytest.raises(ParallelAgentError) as caught:
        for mode, chunk in graph.stream(
            workflow_to_graph_state(context),
            stream_mode=["updates", "values"],
        ):
            if mode == "values":
                results.update(chunk.get("agent_results", {}))
            else:
                for node_update in chunk.values():
                    if isinstance(node_update, dict):
                        results.update(node_update.get("agent_results", {}))

    assert caught.value.agent_name == AgentName.VIDEO
    assert AgentName.VOICE in results
    assert AgentName.EDITOR not in results


def test_parallel_failures_choose_video_and_combine_errors():
    context = _context_through_storyboard()
    agents = _agents_with_assets(
        video=FailingAgent(AgentName.VIDEO, "video quota"),
        voice=FailingAgent(AgentName.VOICE, "voice quota"),
        editor=RecordingAgent(AgentName.EDITOR, []),
    )

    with pytest.raises(ParallelAgentError) as caught:
        list(
            build_pipeline_graph(agents).stream(
                workflow_to_graph_state(context),
                stream_mode="values",
            )
        )

    assert caught.value.agent_name == AgentName.VIDEO
    assert str(caught.value) == "video: video quota; voice: voice quota"
