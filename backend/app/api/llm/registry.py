"""LLM provider registry — factory that returns the configured provider.

Configuration now comes from the llm_settings/llm_providers tables (via
services/llm_service.get_llm_config → base.LLMConfig), not directly from
env: the Settings → AI UI edits those rows at runtime. "harness"/"api"
are the two user-facing backends (plus "stub" for dev/tests); the old env
names (opencode/openai_compatible) still map through the seed fallback.
"""
from app.api.llm.base import AbstractLLMProvider, LLMConfig
from app.api.llm.stub import StubProvider


def get_provider(config: LLMConfig) -> AbstractLLMProvider:
    name = config.mode

    if name == "harness":
        from app.api.llm.opencode_harness import OpenCodeHarnessProvider
        return OpenCodeHarnessProvider(base_url=config.harness_url)

    if name == "api":
        from app.api.llm.openai_compatible import OpenAICompatibleProvider
        return OpenAICompatibleProvider(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )

    if name == "stub":
        return StubProvider()

    raise ValueError(
        f"Unknown LLM backend mode '{name}'. Available: harness, api, stub"
    )
