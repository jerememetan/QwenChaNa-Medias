"""LLM service abstraction — agents call this interface, never raw APIs."""

from abc import ABC, abstractmethod

import openai

from backend.config import LLMConfig
from models.enums import AgentName


class LLMService(ABC):
    """Abstract interface for LLM generation.

    Agents call ``llm_service.generate(prompt, agent_name)`` — the concrete
    provider implementation (AlibabaCloudLLMService, etc.) is injected at
    runtime, so swapping providers requires only a new subclass and a config
    change, not agent code changes.
    """

    @abstractmethod
    def generate(self, prompt: str, agent_name: AgentName) -> str:
        """Generate text from the configured LLM provider.

        Args:
            prompt: The input prompt for generation.
            agent_name: The agent requesting generation (for logging/routing).

        Returns:
            The generated text response.
        """
        ...


class AlibabaCloudLLMService(LLMService):
    """Concrete LLM service using OpenAI-compatible SDK against Alibaba Cloud DashScope."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._client = openai.OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
        )

    def generate(self, prompt: str, agent_name: AgentName) -> str:
        response = self._client.chat.completions.create(
            model=self.config.model,
            messages=[
                {
                    "role": "system",
                    "content": f"You are the {agent_name.value} agent in a video production pipeline. Respond with structured JSON matching the expected output schema.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
