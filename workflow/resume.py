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

    # Filter out agents whose results are already in agent_results
    remaining_agents = [
        agent for agent in agents if agent.name not in context.agent_results
    ]

    # Use Pipeline to run remaining agents
    pipeline = Pipeline(storage)
    return pipeline.run(job_id, remaining_agents, context)
