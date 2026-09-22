"""LLM provider registry — factory that returns the configured provider.

Selects provider by settings.llm_provider name. No hardcoded third-party
services: anything OpenAI-compatible is configured purely via base_url /
api_key / model.
"""
from app.api.llm.base import AbstractLLMProvider
from app.api.llm.stub import StubProvider
from app.core.config import Settings


def get_provider(settings: Settings) -> AbstractLLMProvider:
    name = settings.llm_provider

    if name == "opencode":
        from app.api.llm.opencode_harness import OpenCodeHarnessProvider
        return OpenCodeHarnessProvider(base_url=settings.opencode_url)

    if name == "openai_compatible":
        from app.api.llm.openai_compatible import OpenAICompatibleProvider
        return OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )

    if name == "stub":
        return StubProvider()

    available = "stub, opencode, openai_compatible"
    raise ValueError(
        f"Unknown LLM provider '{name}'. Available: {available}"
    )
