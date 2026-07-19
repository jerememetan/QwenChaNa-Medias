from __future__ import annotations

import operator
from datetime import datetime, timezone
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.base import BaseAgent
from models.agent_result import AgentResult
from models.brief import CreativeBrief
from models.enums import AgentName, JobStatus
from models.workflow_state import WorkflowState


class BranchFailure(TypedDict):
    agent_name: AgentName
    error: str


def merge_agent_results(
    current: dict[AgentName, AgentResult],
    update: dict[AgentName, AgentResult],
) -> dict[AgentName, AgentResult]:
    return {**current, **update}


class PipelineGraphState(TypedDict):
    job_id: str
    prompt: str
    created_at: datetime
    agent_results: Annotated[
        dict[AgentName, AgentResult],
        merge_agent_results,
    ]
    branch_failures: Annotated[list[BranchFailure], operator.add]


class AgentNodeError(RuntimeError):
    def __init__(self, agent_name: AgentName, message: str) -> None:
        self.agent_name = agent_name
        super().__init__(message)


class ParallelAgentError(RuntimeError):
    def __init__(self, failures: list[BranchFailure]) -> None:
        ordered = sorted(
            failures,
            key=lambda item: (
                0 if item["agent_name"] == AgentName.VIDEO else 1,
                item["agent_name"].value,
            ),
        )
        self.failures = ordered
        self.agent_name = ordered[0]["agent_name"]
        message = "; ".join(
            f"{item['agent_name'].value}: {item['error']}" for item in ordered
        )
        super().__init__(message)


def workflow_to_graph_state(context: WorkflowState) -> PipelineGraphState:
    return {
        "job_id": context.job_id,
        "prompt": context.prompt,
        "created_at": context.created_at,
        "agent_results": dict(context.agent_results),
        "branch_failures": [],
    }


def graph_state_to_workflow(
    state: PipelineGraphState,
    status: JobStatus = JobStatus.RUNNING,
) -> WorkflowState:
    return WorkflowState(
        job_id=state["job_id"],
        prompt=state["prompt"],
        status=status,
        current_agent=None,
        agent_results=dict(state.get("agent_results", {})),
        created_at=state["created_at"],
        updated_at=datetime.now(timezone.utc),
    )


def make_agent_node(agent: BaseAgent, capture_failure: bool = False):
    def node(state: PipelineGraphState) -> dict:
        if agent.name in state.get("agent_results", {}):
            return {}
        context = graph_state_to_workflow(state)
        try:
            result = agent.run(context.model_copy(deep=True))
        except Exception as exc:
            if capture_failure:
                return {
                    "branch_failures": [
                        {"agent_name": agent.name, "error": str(exc)}
                    ]
                }
            raise AgentNodeError(agent.name, str(exc)) from exc
        agent_result = result.agent_results.get(agent.name)
        if agent_result is None:
            raise AgentNodeError(
                agent.name,
                f"Agent {agent.name.value} returned no AgentResult",
            )
        return {"agent_results": {agent.name: agent_result}}

    return node


FULL_PIPELINE = [
    AgentName.DIRECTOR,
    AgentName.RESEARCH,
    AgentName.SCRIPT,
    AgentName.STORYBOARD,
    AgentName.VIDEO,
    AgentName.VOICE,
    AgentName.EDITOR,
]


def _index_agents(agents: list[BaseAgent]) -> dict[AgentName, BaseAgent]:
    indexed: dict[AgentName, BaseAgent] = {}
    for agent in agents:
        if agent.name in indexed:
            raise ValueError(f"Duplicate pipeline agent: {agent.name.value}")
        indexed[agent.name] = agent
    return indexed


def _route_research(state: PipelineGraphState) -> str:
    if AgentName.RESEARCH in state.get("agent_results", {}):
        return "research"
    result = state["agent_results"][AgentName.DIRECTOR]
    try:
        brief = CreativeBrief.model_validate(result.output_data)
    except Exception:
        return "research"
    return "research" if brief.requires_research else "skip_research"


def _asset_join(state: PipelineGraphState) -> dict:
    failures = state.get("branch_failures", [])
    if failures:
        raise ParallelAgentError(failures)
    missing = [
        name.value
        for name in (AgentName.VIDEO, AgentName.VOICE)
        if name not in state.get("agent_results", {})
    ]
    if missing:
        raise AgentNodeError(
            AgentName.VIDEO,
            f"Asset join missing successful results: {', '.join(missing)}",
        )
    return {}


def _build_full_graph(indexed: dict[AgentName, BaseAgent]):
    builder = StateGraph(PipelineGraphState)
    builder.add_node("director", make_agent_node(indexed[AgentName.DIRECTOR]))
    builder.add_node("research", make_agent_node(indexed[AgentName.RESEARCH]))
    builder.add_node(
        "skip_research",
        make_agent_node(indexed[AgentName.RESEARCH]),
    )
    builder.add_node("script", make_agent_node(indexed[AgentName.SCRIPT]))
    builder.add_node(
        "storyboard",
        make_agent_node(indexed[AgentName.STORYBOARD]),
    )
    builder.add_node(
        "video",
        make_agent_node(indexed[AgentName.VIDEO], capture_failure=True),
    )
    builder.add_node(
        "voice",
        make_agent_node(indexed[AgentName.VOICE], capture_failure=True),
    )
    builder.add_node("asset_join", _asset_join)
    builder.add_node("editor", make_agent_node(indexed[AgentName.EDITOR]))
    builder.add_edge(START, "director")
    builder.add_conditional_edges(
        "director",
        _route_research,
        {"research": "research", "skip_research": "skip_research"},
    )
    builder.add_edge("research", "script")
    builder.add_edge("skip_research", "script")
    builder.add_edge("script", "storyboard")
    builder.add_edge("storyboard", "video")
    builder.add_edge("storyboard", "voice")
    builder.add_edge(["video", "voice"], "asset_join")
    builder.add_edge("asset_join", "editor")
    builder.add_edge("editor", END)
    return builder.compile()


def _build_compatibility_graph(agents: list[BaseAgent]):
    builder = StateGraph(PipelineGraphState)
    if not agents:
        return None
    names: list[str] = []
    for index, agent in enumerate(agents):
        node_name = f"{index:03d}_{agent.name.value}"
        names.append(node_name)
        builder.add_node(node_name, make_agent_node(agent))
    builder.add_edge(START, names[0])
    for current, following in zip(names, names[1:]):
        builder.add_edge(current, following)
    builder.add_edge(names[-1], END)
    return builder.compile()


def build_pipeline_graph(agents: list[BaseAgent]):
    indexed = _index_agents(agents)
    if list(indexed) == FULL_PIPELINE and len(agents) == len(FULL_PIPELINE):
        return _build_full_graph(indexed)
    return _build_compatibility_graph(agents)
