import os

import pytest

from backend.config import Settings


class TestConfig:
    def test_settings_loads_defaults(self):
        """Settings instantiates with sensible defaults when no env vars are set."""
        settings = Settings()
        assert settings.OUTPUT_DIR == "./outputs"
        assert settings.HOST == "0.0.0.0"
        assert settings.PORT == 8000

    def test_settings_reads_env_vars(self, monkeypatch):
        """Settings picks up values from environment variables."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
        settings = Settings()
        assert settings.OPENAI_API_KEY == "sk-test-123"
        assert settings.OPENAI_MODEL == "gpt-4o-mini"

    def test_settings_output_dir_default(self):
        """Default OUTPUT_DIR is './outputs'."""
        settings = Settings()
        assert settings.OUTPUT_DIR == "./outputs"

    def test_settings_storage_backend_default(self):
        """Default STORAGE_BACKEND is 'local'."""
        settings = Settings()
        assert settings.STORAGE_BACKEND == "local"