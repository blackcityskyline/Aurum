"""LLM settings/provider CRUD and runtime-config resolution.

The chat backend switched from env-only config to DB-backed config so the
UI (Settings → AI) can manage it: pick harness (opencode serve) vs api
(OpenAI-compatible), keep several providers, choose any model. Env vars
(AURUM_LLM_*) remain the fallback that seeds the singleton row on first
use, so an existing deployment keeps working without reconfiguration.
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.llm.base import LLMConfig
from app.core.config import get_settings
from app.models.llm import LlmProvider, LlmSettings
from app.schemas.llm import LlmProviderRead

# Env AURUM_LLM_PROVIDER → DB mode. Kept in one place because the env
# values are the historical names ("opencode", "openai_compatible") while
# the UI speaks the shorter "harness"/"api".
_ENV_MODE_MAP = {
    "opencode": "harness",
    "openai_compatible": "api",
    "stub": "stub",
}


async def get_or_create_llm_settings(session: AsyncSession) -> LlmSettings:
    """Singleton row (id=1), same get-or-create contract as
    get_or_create_app_settings — seeded from the env vars on first access
    so a pre-existing AURUM_LLM_* setup keeps working after upgrade."""
    settings = await session.get(LlmSettings, 1)
    if settings is not None:
        return settings

    env = get_settings()
    settings = LlmSettings(
        id=1,
        mode=_ENV_MODE_MAP.get(env.llm_provider, "harness"),
        harness_url=env.opencode_url,
        max_tokens=env.llm_max_tokens,
        temperature=env.llm_temperature,
    )
    session.add(settings)

    # Carry over a pre-configured openai_compatible endpoint as the first
    # provider row instead of dropping it on the floor.
    if env.llm_base_url:
        provider = LlmProvider(
            name="Configured API",
            base_url=env.llm_base_url,
            api_key=env.llm_api_key or None,
            model=env.llm_model or None,
        )
        session.add(provider)
        await session.flush()
        settings.active_provider_id = provider.id

    await session.commit()
    await session.refresh(settings)
    return settings


async def list_providers(session: AsyncSession, active_id: int | None) -> list[LlmProviderRead]:
    rows = (await session.execute(select(LlmProvider).order_by(LlmProvider.id))).scalars().all()
    return [
        LlmProviderRead(
            id=p.id,
            name=p.name,
            base_url=p.base_url,
            model=p.model,
            has_api_key=bool(p.api_key),
            is_active=p.id == active_id,
        )
        for p in rows
    ]


async def get_provider_or_404(session: AsyncSession, provider_id: int) -> LlmProvider:
    provider = await session.get(LlmProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


async def get_llm_config(session: AsyncSession) -> LLMConfig:
    """Resolve the effective chat config: DB row + active provider, env as
    the fallback when the DB has no active provider (fresh install that
    still only has env vars)."""
    settings = await get_or_create_llm_settings(session)
    config = LLMConfig(
        mode=settings.mode,
        harness_url=settings.harness_url,
        max_tokens=settings.max_tokens,
        temperature=settings.temperature,
    )

    if settings.mode == "api" and settings.active_provider_id is not None:
        provider = await session.get(LlmProvider, settings.active_provider_id)
        if provider is not None:
            config.base_url = provider.base_url
            config.api_key = provider.api_key or ""
            config.model = provider.model or ""
    elif settings.mode == "api":
        # No provider row yet — fall back to env (fresh install path).
        env = get_settings()
        config.base_url = env.llm_base_url
        config.api_key = env.llm_api_key
        config.model = env.llm_model

    return config
