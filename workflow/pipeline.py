"""Sequential pipeline — runs agents in order, persists context after each."""

from datetime import datetime, timezone

from agents.base import BaseAgent
from models.enums import JobStatus
from models.workflow_state import WorkflowState
from storage.base import StorageBackend


class Pipeline:
    def __init__(self, storage: StorageBackend) -> None:
        self.storage = storage

    def run(
        self, job_id: str, agents: list[BaseAgent], context: WorkflowState
    ) -> WorkflowState:
        """Runs agents sequentially. Persists context after each. Returns final context."""
        context.status = JobStatus.RUNNING

        for agent in agents:
            context.current_agent = agent.name
            try:
                context = agent.run(context)
            except Exception as exc:
                context.status = JobStatus.FAILED
                context.failed_agent = agent.name
                context.error = str(exc)
                context.current_agent = None
                context.updated_at = datetime.now(timezone.utc)
                self._persist_context(job_id, context)
                return context

            context.updated_at = datetime.now(timezone.utc)
            self._persist_context(job_id, context)

        context.status = JobStatus.COMPLETED
        context.current_agent = None
        context.updated_at = datetime.now(timezone.utc)
        self._persist_context(job_id, context)
        return context

    def _persist_context(self, job_id: str, context: WorkflowState) -> None:
        data = context.model_dump(mode="json")
        self.storage.save(job_id, "pipeline", "context.json", data)
