import pytest

from backend.config import Settings, LLMConfig, VoiceConfig, VideoConfig, StorageConfig, ServerConfig


class TestConfig:
    def test_settings_loads_defaults(self):
        """Settings instantiates with service-oriented defaults."""
        settings = Settings()
        assert settings.LLM_PROVIDER == "alibaba_cloud_model_studio"
        assert settings.LLM_API_KEY == ""
        assert settings.LLM_BASE_URL == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert settings.LLM_MODEL == "qwen-plus"
        assert settings.LLM_TIMEOUT == 60
        assert settings.VOICE_PROVIDER == "elevenlabs"
        assert settings.VIDEO_PROVIDER == "runway"
        assert settings.STORAGE_BACKEND == "local"
        assert settings.STORAGE_OUTPUT_DIR == "./outputs"
        assert settings.SERVER_HOST == "0.0.0.0"
        assert settings.SERVER_PORT == 8000

    def test_settings_llm_reads_env_vars(self, monkeypatch):
        """LLM_ prefixed env vars override defaults."""
        monkeypatch.setenv("LLM_API_KEY", "sk-test-123")
        monkeypatch.setenv("LLM_MODEL", "qwen-max")
        settings = Settings()
        assert settings.LLM_API_KEY == "sk-test-123"
        assert settings.LLM_MODEL == "qwen-max"

    def test_settings_llm_property_groups_fields(self):
        """settings.llm returns an LLMConfig grouping all LLM fields."""
        settings = Settings()
        llm = settings.llm
        assert isinstance(llm, LLMConfig)
        assert llm.provider == "alibaba_cloud_model_studio"
        assert llm.api_key == ""
        assert llm.model == "qwen-plus"
        assert llm.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert llm.timeout == 60

    def test_settings_llm_property_reflects_env_vars(self, monkeypatch):
        """settings.llm reflects env-var overrides, not just defaults."""
        monkeypatch.setenv("LLM_API_KEY", "sk-live-456")
        monkeypatch.setenv("LLM_MODEL", "qwen-turbo")
        settings = Settings()
        assert settings.llm.api_key == "sk-live-456"
        assert settings.llm.model == "qwen-turbo"

    def test_settings_storage_defaults(self):
        """Storage sub-model defaults: backend=local, output_dir=./outputs."""
        settings = Settings()
        assert settings.storage.backend == "local"
        assert settings.storage.output_dir == "./outputs"

    def test_settings_server_defaults(self):
        """Server sub-model defaults: host=0.0.0.0, port=8000."""
        settings = Settings()
        assert settings.server.host == "0.0.0.0"
        assert settings.server.port == 8000

    def test_llm_config_standalone(self):
        """LLMConfig can be instantiated standalone with defaults."""
        config = LLMConfig()
        assert config.provider == "alibaba_cloud_model_studio"
        assert config.model == "qwen-plus"
