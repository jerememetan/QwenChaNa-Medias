"""Base agent abstraction — every agent implements this interface."""

from abc import ABC, abstractmethod

from models.enums import AgentName
from models.workflow_state import WorkflowState


class BaseAgent(ABC):
    """Abstract base for all pipeline agents.

    Every agent must declare a `name` (AgentName) and implement `run(context)`.
    The pipeline orchestrator calls `agent.run(ctx)` sequentially, passing
    WorkflowState between agents.
    """

    name: AgentName

    @abstractmethod
    def run(self, context: WorkflowState) -> WorkflowState:
        """Execute the agent's work, modifying and returning the context."""
        ...

    def __init__(self) -> None:
        if not hasattr(self, "name") or self.name is None:
            raise TypeError(f"Agent {self.__class__.__name__} must define a 'name' attribute")
        super().__init__()
