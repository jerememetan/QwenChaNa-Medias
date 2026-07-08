from abc import ABC

import pytest

from models.enums import AgentName
from tools.llm import LLMService


class StubLLMService(LLMService):
    """Minimal concrete subclass for testing the ABC contract."""

    def generate(self, prompt: str, agent_name: AgentName) -> str:
        return f"stub-response-for-{agent_name}"


class IncompleteLLMService(LLMService):
    """Subclass missing generate() — used to verify abstract enforcement."""

    pass


class TestLLMService:
    def test_llm_service_is_abstract(self):
        """LLMService cannot be instantiated directly."""
        with pytest.raises(TypeError):
            LLMService()

    def test_llm_service_requires_generate(self):
        """Subclass without generate() raises TypeError on instantiation."""
        with pytest.raises(TypeError):
            IncompleteLLMService()

    def test_concrete_llm_service_can_be_instantiated(self):
        """A subclass implementing generate() can be instantiated."""
        service = StubLLMService()
        assert isinstance(service, LLMService)

    def test_concrete_llm_service_generate_returns_string(self):
        """generate() returns a string for valid inputs."""
        service = StubLLMService()
        result = service.generate("test prompt", AgentName.DIRECTOR)
        assert isinstance(result, str)
        assert result == "stub-response-for-director"
