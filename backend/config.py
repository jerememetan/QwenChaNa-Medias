"""Application configuration via environment variables and .env files.

Service-oriented design: flat env vars are grouped by service prefix
(LLM_, VOICE_, VIDEO_, STORAGE_, SERVER_), and read-only properties
provide typed, grouped access via Pydantic BaseModel sub-models.
"""

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseModel):
    """LLM service configuration — provider-agnostic data container."""

    provider: str = "alibaba_cloud_model_studio"
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-plus"
    timeout: int = 60


class VoiceConfig(BaseModel):
    """Voice/TTS service configuration."""

    provider: str = "elevenlabs"
    api_key: str = ""


class VideoConfig(BaseModel):
    """Video generation service configuration."""

    provider: str = "runway"
    api_key: str = ""


class StorageConfig(BaseModel):
    """Storage backend configuration."""

    backend: str = "local"
    output_dir: str = "./outputs"


class ServerConfig(BaseModel):
    """HTTP server configuration."""

    host: str = "0.0.0.0"
    port: int = 8000


class Settings(BaseSettings):
    """Top-level application settings — flat env vars with grouped access."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ---- LLM ----
    LLM_PROVIDER: str = "alibaba_cloud_model_studio"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL: str = "qwen-plus"
    LLM_TIMEOUT: int = 60

    # ---- Voice ----
    VOICE_PROVIDER: str = "elevenlabs"
    VOICE_API_KEY: str = ""

    # ---- Video ----
    VIDEO_PROVIDER: str = "runway"
    VIDEO_API_KEY: str = ""

    # ---- Storage ----
    STORAGE_BACKEND: str = "local"
    STORAGE_OUTPUT_DIR: str = "./outputs"

    # ---- Server ----
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000

    @property
    def llm(self) -> LLMConfig:
        return LLMConfig(
            provider=self.LLM_PROVIDER,
            api_key=self.LLM_API_KEY,
            base_url=self.LLM_BASE_URL,
            model=self.LLM_MODEL,
            timeout=self.LLM_TIMEOUT,
        )

    @property
    def voice(self) -> VoiceConfig:
        return VoiceConfig(
            provider=self.VOICE_PROVIDER,
            api_key=self.VOICE_API_KEY,
        )

    @property
    def video(self) -> VideoConfig:
        return VideoConfig(
            provider=self.VIDEO_PROVIDER,
            api_key=self.VIDEO_API_KEY,
        )

    @property
    def storage(self) -> StorageConfig:
        return StorageConfig(
            backend=self.STORAGE_BACKEND,
            output_dir=self.STORAGE_OUTPUT_DIR,
        )

    @property
    def server(self) -> ServerConfig:
        return ServerConfig(
            host=self.SERVER_HOST,
            port=self.SERVER_PORT,
        )
