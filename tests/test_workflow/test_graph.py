from unittest.mock import MagicMock

from agents.base import BaseAgent
from agents.research import ResearchAgent
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from models.enums import AgentName
from models.workflow_state import WorkflowState
from storage.local import LocalStorage
from tools.llm import LLMService
from workflow.graph import build_pipeline_graph, workflow_to_graph_state


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
