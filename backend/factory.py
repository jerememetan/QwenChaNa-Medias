from pathlib import Path

from agents.base import BaseAgent
from agents.director import DirectorAgent
from agents.editor import EditorAgent
from agents.research import ResearchAgent
from agents.script import ScriptAgent
from agents.storyboard import StoryboardAgent
from agents.video import VideoAgent
from agents.voice import VoiceAgent
from backend.config import Settings
from storage.base import StorageBackend
from tools.ffmpeg import LocalFFmpegService
from tools.llm import AlibabaCloudLLMService
from tools.tts import DashScopeTTSService
from tools.video_gen import DashScopeVideoGenService


def build_production_agents(
    settings: Settings,
    storage: StorageBackend,
    output_dir: str | Path,
    fallback_enabled: bool = False,
) -> list[BaseAgent]:
    llm = AlibabaCloudLLMService(settings.llm)
    video = DashScopeVideoGenService(settings.video)
    voice = DashScopeTTSService(settings.voice)
    return [
        DirectorAgent(llm, storage),
        ResearchAgent(llm, storage),
        ScriptAgent(llm, storage),
        StoryboardAgent(llm, storage),
        VideoAgent(
            video,
            storage=storage,
            fallback_enabled=fallback_enabled,
            output_dir=output_dir,
        ),
        VoiceAgent(
            voice,
            storage=storage,
            fallback_enabled=fallback_enabled,
            output_dir=output_dir,
        ),
        EditorAgent(LocalFFmpegService(), storage, output_dir),
    ]
