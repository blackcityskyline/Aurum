"""LLM provider registry — factory that returns the configured provider."""
from app.api.llm.base import AbstractLLMProvider
from app.api.llm.stub import StubProvider
from app.core.config import Settings


def get_provider(settings: Settings) -> AbstractLLMProvider:
    """Return an LLM provider instance based on settings.llm_provider.

    Adding a new provider:
    1. Create app/api/llm/my_provider.py implementing AbstractLLMProvider
    2. Import it here and add a branch in the mapping below
    """
    providers: dict[str, type[AbstractLLMProvider]] = {
        "stub": StubProvider,
    }

    # Lazy import — only load provider if configured (avoids missing deps)
    provider_name = settings.llm_provider
    if provider_name not in providers:
        if provider_name == "opencode-zen":
            from app.api.llm.opencode_zen import OpenCodeZenProvider
            providers["opencode-zen"] = OpenCodeZenProvider
        elif provider_name == "groq":
            from app.api.llm.groq import GroqProvider
            providers["groq"] = GroqProvider

    provider_cls = providers.get(provider_name)
    if provider_cls is None:
        available = ", ".join(sorted(providers.keys()))
        raise ValueError(
            f"Unknown LLM provider '{provider_name}'. "
            f"Available: {available}"
        )
    return provider_cls()
