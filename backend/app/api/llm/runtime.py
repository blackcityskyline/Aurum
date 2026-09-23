"""Network side of chat-backend configuration: model catalogue fetch and
connectivity test. Kept separate from routes (which own HTTP semantics)
and from llm_service (which owns DB rows) so each stays testable alone."""
import httpx

from app.api.llm.base import LLMConfig

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def _headers(api_key: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def fetch_models(base_url: str, api_key: str | None) -> list[str]:
    """GET {base_url}/models and flatten it across the two shapes real
    endpoints use: OpenAI/OpenRouter's {data: [{id}]} and Ollama's
    {models: [{name}]}. Deduplicated + sorted, free models first (they're
    the default answer for a self-hosted setup without a paid key)."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(f"{base_url.rstrip('/')}/models", headers=_headers(api_key))
        resp.raise_for_status()
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
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            base = config.harness_url.rstrip("/")
            resp = await client.post(f"{base}/session", json={})
            resp.raise_for_status()
            session_id = resp.json().get("id")
            if session_id:
                await client.delete(f"{base}/session/{session_id}")
        return f"Harness at {config.harness_url} is reachable"

    if not config.base_url:
        raise ValueError("No API provider configured — add one in Settings → AI")
    models = await fetch_models(config.base_url, config.api_key or None)
    return f"API endpoint reachable, {len(models)} models available"
