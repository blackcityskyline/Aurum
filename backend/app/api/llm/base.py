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
class HarnessModel:
    """One model a harness offers — generic on purpose: `id` is an opaque
    driver-side string ("opencode/big-pickle"), and the UI just renders
    label/provider/context without knowing which harness produced it."""

    id: str
    label: str
    provider: str
    context: int | None = None
    tool_calling: bool = False


@dataclass
class LLMConfig:
    """Resolved runtime configuration for the chat AI — built from the
    llm_settings/llm_providers tables (see services/llm_service.py), with
    the env vars as a fresh-install fallback."""

    mode: str = "harness"  # harness | api | stub
    # Which harness driver answers (key into registry.HARNESSES) and
    # which model inside it to pin — NULL/empty means the harness default.
    harness_type: str = "opencode"
    harness_model: str = ""
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


class HarnessProvider(AbstractLLMProvider):
    """Chat backend that *is* an external agent harness (opencode today,
    something else eventually). Extends the plain chat contract with the
    two things the Settings/chat UI asks of a harness:

    - list_models(): its model catalogue (generic HarnessModel rows);
    - health():      a cheap round-trip proving it answers.

    Both default to NotImplementedError instead of being abstract, so a
    harness that manages its own models (no catalogue to expose) only has
    to implement chat() and leaves supports_model_choice = False — the UI
    then degrades to a plain badge, no special-casing needed.
    """

    # Registry key (llm_settings.harness_type), e.g. "opencode".
    type: str = ""
    # Whether this harness exposes a selectable model catalogue at all.
    supports_model_choice: bool = False

    async def list_models(self) -> list[HarnessModel]:
        """Model catalogue, or raise if this harness has none."""
        raise NotImplementedError(f"{type(self).__name__} exposes no model catalogue")

    async def health(self) -> str:
        """One cheap round-trip; return a human-readable detail string."""
        raise NotImplementedError(f"{type(self).__name__} has no health check")
