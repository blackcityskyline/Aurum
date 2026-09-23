"""LLM provider registry — factory that returns the configured provider.

Configuration now comes from the llm_settings/llm_providers tables (via
services/llm_service.get_llm_config → base.LLMConfig), not directly from
env: the Settings → AI UI edits those rows at runtime. "harness"/"api"
are the two user-facing backends (plus "stub" for dev/tests); the old env
names (opencode/openai_compatible) still map through the seed fallback.

Harness drivers are looked up by llm_settings.harness_type through
HARNESSES — adding a different harness is one module implementing
base.HarnessProvider plus one line here, no other code changes.
"""
from collections.abc import Callable

from app.api.llm.base import AbstractLLMProvider, HarnessProvider, LLMConfig
from app.api.llm.stub import StubProvider

# harness_type → driver factory. Kept as factories (not classes) so each
# driver can pick up its own config fields without the registry knowing
# their internals.
HARNESSES: dict[str, Callable[[LLMConfig], HarnessProvider]] = {}


def _opencode(config: LLMConfig) -> HarnessProvider:
    from app.api.llm.opencode_harness import OpenCodeHarnessProvider

    return OpenCodeHarnessProvider(
        base_url=config.harness_url,
        model=config.harness_model or None,
    )


HARNESSES["opencode"] = _opencode


def get_harness(config: LLMConfig) -> HarnessProvider:
    """Build the harness driver named by config.harness_type. Separate
    from get_provider because the routes (model catalogue, health) need
    the harness interface specifically, not just anything chat-able."""
    build = HARNESSES.get(config.harness_type)
    if build is None:
        raise ValueError(
            f"Unknown harness type '{config.harness_type}'. "
            f"Available: {', '.join(sorted(HARNESSES))}"
        )
    return build(config)


def get_provider(config: LLMConfig) -> AbstractLLMProvider:
    name = config.mode

    if name == "harness":
        return get_harness(config)

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
