"""Storage backend abstraction — agents persist artifacts through this interface."""

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """Abstract interface for artifact persistence.

    All agents and the pipeline save/load artifacts through this interface.
    Concrete implementations (LocalStorage, CloudStorage) are injected at runtime.
    """

    @abstractmethod
    def save(self, job_id: str, agent_name: str, filename: str, data: dict) -> None:
        """Persist a dict as JSON under the agent's output directory."""
        ...

    @abstractmethod
    def load(self, job_id: str, agent_name: str, filename: str) -> dict | None:
        """Load a previously saved artifact. Returns None if file doesn't exist."""
        ...

    @abstractmethod
    def exists(self, job_id: str, agent_name: str, filename: str) -> bool:
        """Check whether an artifact file exists."""
        ...

    @abstractmethod
    def list_artifacts(self, job_id: str, agent_name: str) -> list[str]:
        """List all filenames in an agent's output directory."""
        ...
