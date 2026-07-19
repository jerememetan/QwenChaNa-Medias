"""Sequential pipeline — runs agents in order, persists context after each."""

from datetime import datetime, timezone

from agents.base import BaseAgent
from models.enums import JobStatus
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from workflow.graph import (
    AgentNodeError,
    ParallelAgentError,
    build_pipeline_graph,
    graph_state_to_workflow,
    workflow_to_graph_state,
)


class Pipeline:
    def __init__(self, storage: StorageBackend) -> None:
        self.storage = storage

    def run(
        self, job_id: str, agents: list[BaseAgent], context: WorkflowState
    ) -> WorkflowState:
        """Stream agents through LangGraph and persist every safe state update."""
        context.status = JobStatus.RUNNING
        context.current_agent = None
        context.failed_agent = None
        context.error = None
        context.updated_at = datetime.now(timezone.utc)
        self._persist_context(job_id, context)

        latest = workflow_to_graph_state(context)
        try:
            graph = build_pipeline_graph(agents)
            if graph is None:
                context.status = JobStatus.COMPLETED
                context.updated_at = datetime.now(timezone.utc)
                self._persist_context(job_id, context)
                return context
            for mode, chunk in graph.stream(
                latest,
                stream_mode=["updates", "values"],
            ):
                if mode == "values":
                    latest = chunk
                else:
                    latest = self._apply_update(latest, chunk)
                context = graph_state_to_workflow(latest)
                self._persist_context(job_id, context)
        except (AgentNodeError, ParallelAgentError) as exc:
            context = graph_state_to_workflow(latest, status=JobStatus.FAILED)
            context.failed_agent = exc.agent_name
            context.error = str(exc)
            context.updated_at = datetime.now(timezone.utc)
            self._persist_context(job_id, context)
            return context
        except Exception as exc:
            context = graph_state_to_workflow(latest, status=JobStatus.FAILED)
            context.error = f"Graph execution failed: {exc}"
            context.updated_at = datetime.now(timezone.utc)
            self._persist_context(job_id, context)
            return context

        context = graph_state_to_workflow(latest, status=JobStatus.COMPLETED)
        context.updated_at = datetime.now(timezone.utc)
        self._persist_context(job_id, context)
        return context

    @staticmethod
    def _apply_update(latest: dict, chunk: dict) -> dict:
        merged = dict(latest)
        results = dict(merged.get("agent_results", {}))
        failures = list(merged.get("branch_failures", []))
        for node_update in chunk.values():
            if not isinstance(node_update, dict):
                continue
            results.update(node_update.get("agent_results", {}))
            failures.extend(node_update.get("branch_failures", []))
        merged["agent_results"] = results
        merged["branch_failures"] = failures
        return merged

    def _persist_context(self, job_id: str, context: WorkflowState) -> None:
        data = context.model_dump(mode="json")
        self.storage.save(job_id, "pipeline", "context.json", data)
