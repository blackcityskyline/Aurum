"""Abstract base class for LLM providers."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    """One function call requested by the model (OpenAI tool-calling
    format, regardless of which provider produced it)."""

    id: str
    name: str
    arguments: dict


@dataclass
class LLMResult:
    """What a provider round-trip produced: the assistant text, any tool
    calls it wants us to execute, and the chain-of-thought when the
    provider exposes one (OpenRouter's `reasoning` field for reasoning
    models)."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning: str | None = None


@dataclass
class LLMConfig:
    """Resolved runtime configuration for the chat AI — built from the
    llm_settings/llm_providers tables (see services/llm_service.py), with
    the env vars as a fresh-install fallback."""

    mode: str = "harness"  # harness | api | stub
    harness_url: str = "http://host.docker.internal:4096"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    max_tokens: int = 2048
    temperature: float = 0.7


class AbstractLLMProvider(ABC):
    """All LLM providers must implement this interface.

    `chat` receives OpenAI-style messages ({'role', 'content'}) plus, when
    `supports_tools` is True, JSON-schema tool definitions the model may
    call. The ChatService executes returned tool calls and feeds results
    back in a loop; providers without tool support fall back to the
    prompt-embedded JSON action protocol instead.
    """

    # Whether this backend can do native OpenAI-style tool calling.
    supports_tools: bool = False

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResult:
        """Send messages to the LLM and return its structured result."""
        ...
