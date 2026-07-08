"""LLM service abstraction — agents call this interface, never raw APIs."""

from abc import ABC, abstractmethod

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
