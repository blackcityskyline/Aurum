"""Chat AI backend configuration endpoints (Settings → AI).

Two concerns the routes enforce: API keys never leave the server once
saved (reads report `has_api_key` only), and the active provider is
validated on every switch so a dangling id can't brick the chat.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.llm.registry import HARNESSES, get_harness
from app.api.llm.runtime import fetch_models, test_backend
from app.models.llm import LlmProvider
from app.schemas.llm import (
    HarnessModelRead,
    HarnessModelsResponse,
    LlmModelsRequest,
    LlmModelsResponse,
    LlmProviderCreate,
    LlmProviderRead,
    LlmProviderUpdate,
    LlmSettingsRead,
    LlmSettingsUpdate,
    LlmTestResponse,
)
from app.services.llm_service import (
    get_llm_config,
    get_or_create_llm_settings,
    get_provider_or_404,
    list_providers,
)

router = APIRouter(prefix="/llm", tags=["llm"])


async def _read(session: AsyncSession) -> LlmSettingsRead:
    settings = await get_or_create_llm_settings(session)
    return LlmSettingsRead(
        mode=settings.mode,
        harness_type=settings.harness_type,
        harness_url=settings.harness_url,
        harness_model=settings.harness_model,
        max_tokens=settings.max_tokens,
        temperature=settings.temperature,
        active_provider_id=settings.active_provider_id,
        providers=await list_providers(session, settings.active_provider_id),
    )


@router.get("/config", response_model=LlmSettingsRead)
async def read_config(session: AsyncSession = Depends(get_session)) -> LlmSettingsRead:
    return await _read(session)


@router.patch("/config", response_model=LlmSettingsRead)
async def update_config(
    payload: LlmSettingsUpdate, session: AsyncSession = Depends(get_session)
) -> LlmSettingsRead:
    settings = await get_or_create_llm_settings(session)

    data = payload.model_dump(exclude_unset=True)
    if "active_provider_id" in data:
        provider_id = data["active_provider_id"]
        if provider_id is not None and await session.get(LlmProvider, provider_id) is None:
            raise HTTPException(status_code=400, detail="Provider not found")
    # Validated against the driver registry (not a schema Literal) so a
    # new harness ships by adding to HARNESSES — schemas stay untouched.
    if "harness_type" in data and data["harness_type"] not in HARNESSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown harness type '{data['harness_type']}'. "
                f"Available: {', '.join(sorted(HARNESSES))}"
            ),
        )
    if "harness_model" in data:
        # "" (the picker's "default" option) and null both mean "no pin".
        data["harness_model"] = data["harness_model"] or None
    # LlmSettingsUpdate.mode is Literal[harness, api] — "stub" stays
    # reachable only through env/direct SQL on purpose (it's a dev mode).
    for field, value in data.items():
        setattr(settings, field, value)
    await session.commit()
    return await _read(session)


@router.post("/providers", response_model=LlmProviderRead, status_code=201)
async def create_provider(
    payload: LlmProviderCreate, session: AsyncSession = Depends(get_session)
) -> LlmProviderRead:
    settings = await get_or_create_llm_settings(session)
    provider = LlmProvider(
        name=payload.name,
        base_url=payload.base_url.rstrip("/"),
        api_key=payload.api_key or None,
        model=payload.model or None,
    )
    session.add(provider)
    await session.flush()
    if payload.activate or settings.active_provider_id is None:
        settings.active_provider_id = provider.id
    await session.commit()

    provider = await get_provider_or_404(session, provider.id)
    return _provider_read(provider, settings.active_provider_id)


@router.patch("/providers/{provider_id}", response_model=LlmProviderRead)
async def update_provider(
    provider_id: int,
    payload: LlmProviderUpdate,
    session: AsyncSession = Depends(get_session),
) -> LlmProviderRead:
    settings = await get_or_create_llm_settings(session)
    provider = await get_provider_or_404(session, provider_id)

    data = payload.model_dump(exclude_unset=True)
    activate = data.pop("activate", None)
    # api_key: omitted → unchanged; null/"" → cleared; set → replaced.
    if "api_key" in data:
        data["api_key"] = data["api_key"] or None
    if "base_url" in data and data["base_url"]:
        data["base_url"] = data["base_url"].rstrip("/")
    for field, value in data.items():
        setattr(provider, field, value)
    if activate:
        settings.active_provider_id = provider.id
    elif activate is False and settings.active_provider_id == provider.id:
        settings.active_provider_id = None
    await session.commit()

    provider = await get_provider_or_404(session, provider.id)
    return _provider_read(provider, settings.active_provider_id)


@router.delete("/providers/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    # Not relying solely on the FK's ON DELETE SET NULL for correctness of
    # the response payload — clear it explicitly so the returned config is
    # consistent without a re-read race.
    settings = await get_or_create_llm_settings(session)
    provider = await get_provider_or_404(session, provider_id)
    if settings.active_provider_id == provider.id:
        settings.active_provider_id = None
    await session.delete(provider)
    await session.commit()


@router.post("/models", response_model=LlmModelsResponse)
async def models(
    payload: LlmModelsRequest, session: AsyncSession = Depends(get_session)
) -> LlmModelsResponse:
    """Model catalogue of an OpenAI-compatible endpoint. Two callers: the
    chat picker (provider_id only — the saved row carries url + key) and the
    provider dialog (typed base_url/api_key, optionally with provider_id so a
    stored key doesn't have to be re-entered). A typed url wins over the
    stored one, since the dialog loads models *before* saving the edit."""
    base_url = (payload.base_url or "").strip()
    if payload.provider_id is not None:
        provider = await get_provider_or_404(session, payload.provider_id)
        base_url = base_url or provider.base_url
        api_key = payload.api_key if payload.api_key is not None else provider.api_key
    else:
        api_key = payload.api_key

    if not base_url:
        raise HTTPException(
            status_code=400, detail="Either provider_id or base_url is required"
        )
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400, detail="base_url must start with http:// or https://"
        )
    try:
        return LlmModelsResponse(models=await fetch_models(base_url, api_key))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch models: {e}")


@router.get("/harness/models", response_model=HarnessModelsResponse)
async def harness_models(session: AsyncSession = Depends(get_session)) -> HarnessModelsResponse:
    """Model catalogue of the configured harness driver — generic rows, so
    the chat picker renders identically whatever harness is in charge."""
    config = await get_llm_config(session)
    try:
        models = await get_harness(config).list_models()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch harness models: {e}")
    return HarnessModelsResponse(
        models=[
            HarnessModelRead(
                id=m.id,
                label=m.label,
                provider=m.provider,
                context=m.context,
                tool_calling=m.tool_calling,
            )
            for m in models
        ]
    )


@router.post("/test", response_model=LlmTestResponse)
async def test(session: AsyncSession = Depends(get_session)) -> LlmTestResponse:
    config = await get_llm_config(session)
    try:
        detail = await test_backend(config)
        return LlmTestResponse(ok=True, detail=detail)
    except Exception as e:
        return LlmTestResponse(ok=False, detail=str(e))


def _provider_read(provider: LlmProvider, active_id: int | None) -> LlmProviderRead:
    return LlmProviderRead(
        id=provider.id,
        name=provider.name,
        base_url=provider.base_url,
        model=provider.model,
        has_api_key=bool(provider.api_key),
        is_active=provider.id == active_id,
    )
