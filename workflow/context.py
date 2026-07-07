"""Pipeline context — re-exports WorkflowState with an alias for natural pipeline imports."""

from models.workflow_state import WorkflowState as JobContext

__all__ = ["JobContext"]
