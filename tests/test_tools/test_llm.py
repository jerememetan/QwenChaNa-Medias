from abc import ABC
from unittest.mock import MagicMock, patch

import pytest

from backend.config import LLMConfig
from models.enums import AgentName
from tools.llm import AlibabaCloudLLMService, LLMService


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


class TestAlibabaCloudLLMService:
    def test_can_be_instantiated_with_config(self):
        config = LLMConfig(api_key="test-key", model="qwen-plus")
        service = AlibabaCloudLLMService(config)
        assert service.config.api_key == "test-key"
        assert service.config.model == "qwen-plus"

    def test_generate_calls_openai_client(self):
        config = LLMConfig(
            api_key="test-key",
            model="qwen-plus",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        service = AlibabaCloudLLMService(config)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated text response"

        with patch.object(
            service._client.chat.completions, "create", return_value=mock_response
        ) as mock_create:
            result = service.generate("test prompt", AgentName.DIRECTOR)
            mock_create.assert_called_once()
            assert result == "Generated text response"

    def test_generate_raises_on_api_error(self):
        import openai

        config = LLMConfig(api_key="test-key", model="qwen-plus")
        service = AlibabaCloudLLMService(config)

        with patch.object(
            service._client.chat.completions,
            "create",
            side_effect=openai.APIConnectionError(request=MagicMock()),
        ):
            with pytest.raises(openai.APIConnectionError):
                service.generate("test prompt", AgentName.DIRECTOR)

    def test_generate_passes_model_and_prompt(self):
        config = LLMConfig(
            api_key="test-key",
            model="qwen-plus",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        service = AlibabaCloudLLMService(config)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"

        with patch.object(
            service._client.chat.completions, "create", return_value=mock_response
        ) as mock_create:
            service.generate("my prompt text", AgentName.RESEARCH)
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["model"] == "qwen-plus"
            assert call_kwargs["messages"][1]["content"] == "my prompt text"

    def test_generate_includes_agent_name_in_system_prompt(self):
        config = LLMConfig(api_key="test-key", model="qwen-plus")
        service = AlibabaCloudLLMService(config)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "response"

        with patch.object(
            service._client.chat.completions, "create", return_value=mock_response
        ) as mock_create:
            service.generate("prompt", AgentName.DIRECTOR)
            call_kwargs = mock_create.call_args.kwargs
            system_msg = call_kwargs["messages"][0]
            assert "director" in system_msg["content"].lower()
