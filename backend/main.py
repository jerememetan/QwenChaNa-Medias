"""FastAPI application entry point — creates production app with default storage and agents."""

from storage.local import LocalStorage
from backend.api.routes import create_app
from backend.config import Settings
from models.job import JobRecord
from tools.llm import AlibabaCloudLLMService
from agents.director import DirectorAgent
from agents.research import ResearchAgent
from agents.script import ScriptAgent
from agents.storyboard import StoryboardAgent


def create_production_app():
    settings = Settings()
    storage = LocalStorage(settings.storage.output_dir)
    job_store: dict[str, JobRecord] = {}

    llm_service = AlibabaCloudLLMService(settings.llm)
    agents = [
        DirectorAgent(llm_service=llm_service, storage=storage),
        ResearchAgent(llm_service=llm_service, storage=storage),
        ScriptAgent(llm_service=llm_service, storage=storage),
        StoryboardAgent(llm_service=llm_service, storage=storage),
    ]

    return create_app(storage=storage, job_store=job_store, agents=agents)


app = create_production_app()
