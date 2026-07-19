"""FastAPI application entry point with production storage and agents."""

import os
from pathlib import Path

from backend.api.routes import create_app
from backend.config import Settings
from backend.factory import build_production_agents
from models.job import JobRecord
from storage.local import LocalStorage


def create_production_app():
    initial_settings = Settings()
    storage = LocalStorage(initial_settings.storage.output_dir)
    job_store: dict[str, JobRecord] = {}
    fallback_enabled = os.environ.get("FALLBACK_STUBS", "false").lower() == "true"

    def agent_factory():
        return build_production_agents(
            Settings(),
            storage,
            output_dir=initial_settings.storage.output_dir,
            fallback_enabled=fallback_enabled,
        )

    agents = agent_factory()
    frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    return create_app(
        storage=storage,
        job_store=job_store,
        agents=agents,
        agent_factory=agent_factory,
        frontend_dist=frontend_dist,
    )


app = create_production_app()
