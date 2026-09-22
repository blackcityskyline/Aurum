"""Abstract base class for LLM providers."""
from abc import ABC, abstractmethod


class AbstractLLMProvider(ABC):
    """All LLM providers must implement this interface.

    The chat method receives a list of messages (OpenAI-style dicts with
    'role' and 'content' keys) and returns the assistant's reply as a
    plain string. Providers may ignore the `tools` parameter if they
    don't support tool calling — the ChatService will fall back to
    prompt-based action extraction.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> str:
        """Send messages to the LLM and return the text response."""
        ...
