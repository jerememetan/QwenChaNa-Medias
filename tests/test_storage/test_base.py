from abc import ABC

import pytest

from storage.base import StorageBackend


class IncompleteStorage(StorageBackend):
    """Subclass that only implements save — missing load, exists, list_artifacts."""

    def save(self, job_id: str, agent_name: str, filename: str, data: dict) -> None:
        pass


class CompleteStorage(StorageBackend):
    """Subclass that implements all abstract methods."""

    def save(self, job_id: str, agent_name: str, filename: str, data: dict) -> None:
        pass

    def load(self, job_id: str, agent_name: str, filename: str) -> dict | None:
        return None

    def exists(self, job_id: str, agent_name: str, filename: str) -> bool:
        return False

    def list_artifacts(self, job_id: str, agent_name: str) -> list[str]:
        return []


class TestStorageBackendABC:
    def test_storage_backend_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            StorageBackend()

    def test_storage_backend_requires_save(self):
        with pytest.raises(TypeError):
            IncompleteStorage()

    def test_storage_backend_requires_load(self):
        """IncompleteStorage only has save — it's still missing load, exists, list_artifacts."""
        with pytest.raises(TypeError):
            IncompleteStorage()

    def test_storage_backend_requires_exists(self):
        with pytest.raises(TypeError):
            IncompleteStorage()

    def test_storage_backend_requires_list_artifacts(self):
        with pytest.raises(TypeError):
            IncompleteStorage()

    def test_storage_backend_concrete_implementation_works(self):
        backend = CompleteStorage()
        assert isinstance(backend, StorageBackend)
        assert isinstance(backend, ABC)
