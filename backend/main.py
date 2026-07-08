"""FastAPI application entry point — creates production app with default storage."""

from storage.local import LocalStorage
from backend.api.routes import create_app
from models.job import JobRecord


def create_production_app():
    storage = LocalStorage("./outputs")
    job_store: dict[str, JobRecord] = {}
    return create_app(storage=storage, job_store=job_store)


app = create_production_app()
