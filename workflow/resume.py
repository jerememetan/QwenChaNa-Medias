"""Resume a failed/incomplete job — load context, skip completed agents, run remaining."""

from agents.base import BaseAgent
from models.workflow_state import WorkflowState
from storage.base import StorageBackend
from workflow.pipeline import Pipeline


def resume_job(
    job_id: str, agents: list[BaseAgent], storage: StorageBackend
) -> WorkflowState:
    """Loads persisted context, skips completed agents, runs remaining, returns final context."""
    context_data = storage.load(job_id, "pipeline", "context.json")
    if context_data is None:
        raise FileNotFoundError(
            f"No context.json found for job_id '{job_id}' — cannot resume"
        )

    context = WorkflowState.model_validate(context_data)

    # Clear previous failure markers before retrying
    context.failed_agent = None
    context.error = None

    return Pipeline(storage).run(job_id, agents, context)
