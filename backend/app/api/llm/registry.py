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

    provider_cls = providers.get(settings.llm_provider)
    if provider_cls is None:
        available = ", ".join(sorted(providers.keys()))
        raise ValueError(
            f"Unknown LLM provider '{settings.llm_provider}'. "
            f"Available: {available}"
        )
    return provider_cls()
