"""FastAPI application entry point — creates production app with default storage and agents."""

import os

from storage.local import LocalStorage
from backend.api.routes import create_app
from backend.config import Settings
from models.job import JobRecord
from tools.llm import AlibabaCloudLLMService
from tools.tts import DashScopeTTSService
from tools.video_gen import DashScopeVideoGenService
from agents.director import DirectorAgent
from agents.research import ResearchAgent
from agents.script import ScriptAgent
from agents.storyboard import StoryboardAgent
from agents.video import VideoAgent
from agents.voice import VoiceAgent


def create_production_app():
    settings = Settings()
    storage = LocalStorage(settings.storage.output_dir)
    job_store: dict[str, JobRecord] = {}

    llm_service = AlibabaCloudLLMService(settings.llm)
    tts_service = DashScopeTTSService(settings.voice)
    video_service = DashScopeVideoGenService(settings.video)

    fallback_enabled = os.environ.get("FALLBACK_STUBS", "false").lower() == "true"

    agents = [
        DirectorAgent(llm_service=llm_service, storage=storage),
        ResearchAgent(llm_service=llm_service, storage=storage),
        ScriptAgent(llm_service=llm_service, storage=storage),
        StoryboardAgent(llm_service=llm_service, storage=storage),
        VideoAgent(
            video_service=video_service,
            storage=storage,
            fallback_enabled=fallback_enabled,
        ),
        VoiceAgent(
            tts_service=tts_service,
            storage=storage,
            fallback_enabled=fallback_enabled,
        ),
    ]

    return create_app(storage=storage, job_store=job_store, agents=agents)


app = create_production_app()
