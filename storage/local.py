"""Local filesystem storage backend — persists artifacts as JSON files on disk."""

import json
from pathlib import Path

from storage.base import StorageBackend


class LocalStorage(StorageBackend):
    """File-system backed storage using pathlib.

    Layout: {output_dir}/{job_id}/{agent_name}/{filename}
    """

    def __init__(self, output_dir: str = "./outputs") -> None:
        self.output_dir = Path(output_dir)

    def _artifact_path(self, job_id: str, agent_name: str, filename: str) -> Path:
        return self.output_dir / job_id / agent_name / filename

    def save(self, job_id: str, agent_name: str, filename: str, data: dict) -> None:
        path = self._artifact_path(job_id, agent_name, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def load(self, job_id: str, agent_name: str, filename: str) -> dict | None:
        path = self._artifact_path(job_id, agent_name, filename)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def exists(self, job_id: str, agent_name: str, filename: str) -> bool:
        return self._artifact_path(job_id, agent_name, filename).exists()

    def list_artifacts(self, job_id: str, agent_name: str) -> list[str]:
        agent_dir = self.output_dir / job_id / agent_name
        if not agent_dir.is_dir():
            return []
        return [f.name for f in agent_dir.iterdir() if f.is_file()]
