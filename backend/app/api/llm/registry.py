"""LLM provider registry — factory that returns the configured provider."""
from app.api.llm.base import AbstractLLMProvider
from app.api.llm.stub import StubProvider
from app.core.config import Settings


def get_provider(settings: Settings) -> AbstractLLMProvider:
    """Return an LLM provider instance based on settings.llm_provider.

    Providers:
      - stub:          Echoes input, for testing without any LLM
      - opencode:      Calls a running opencode serve instance (recommended)
    """
    provider_name = settings.llm_provider

    if provider_name == "opencode":
        from app.api.llm.opencode_harness import OpenCodeHarnessProvider
        return OpenCodeHarnessProvider(base_url=settings.opencode_url)

    if provider_name == "stub":
        return StubProvider()

    available = "stub, opencode"
    raise ValueError(
        f"Unknown LLM provider '{provider_name}'. Available: {available}"
    )
