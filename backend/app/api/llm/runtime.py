"""Network side of chat-backend configuration: model catalogue fetch and
connectivity test. Kept separate from routes (which own HTTP semantics)
and from llm_service (which owns DB rows) so each stays testable alone."""
import httpx

from app.api.llm.base import LLMConfig
from app.api.llm.errors import describe_transport_error, describe_upstream_error

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def _headers(api_key: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def fetch_models(base_url: str, api_key: str | None) -> list[str]:
    """GET {base_url}/models and flatten it across the two shapes real
    endpoints use: OpenAI/OpenRouter's {data: [{id}]} and Ollama's
    {models: [{name}]}. Deduplicated + sorted, free models first (they're
    the default answer for a self-hosted setup without a paid key).

    Endpoint failures are re-raised as ValueError with the same readable
    wording the chat path uses (see llm/errors.py), because both callers —
    the models route and the Settings connectivity test — turn ValueError
    straight into a user-facing detail string."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{base_url.rstrip('/')}/models", headers=_headers(api_key)
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise ValueError(describe_upstream_error(e.response, base_url)) from e
    except httpx.HTTPError as e:
        raise ValueError(describe_transport_error(e, base_url)) from e
    body = resp.json()

    if isinstance(body, dict) and isinstance(body.get("data"), list):
        ids = [m.get("id") for m in body["data"] if isinstance(m, dict)]
    elif isinstance(body, dict) and isinstance(body.get("models"), list):
        ids = [m.get("name") for m in body["models"] if isinstance(m, dict)]
    else:
        raise ValueError("Unrecognized /models response shape")

    models = sorted({m for m in ids if m}, key=lambda m: (":free" not in m, m))
    if not models:
        raise ValueError("Endpoint returned no models")
    return models


async def test_backend(config: LLMConfig) -> str:
    """Cheap round-trip proving the configured backend is reachable:
    harness → create+delete an opencode session; api → list models;
    stub → always ok."""
    if config.mode == "stub":
        return "stub backend always answers"

    if config.mode == "harness":
        from app.api.llm.registry import get_harness

        return await get_harness(config).health()

    if not config.base_url:
        raise ValueError("No API provider configured — add one in Settings → AI")
    models = await fetch_models(config.base_url, config.api_key or None)
    return f"API endpoint reachable, {len(models)} models available"
