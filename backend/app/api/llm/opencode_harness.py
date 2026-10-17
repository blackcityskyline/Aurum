"""OpenCode harness driver — calls a running opencode serve instance.

This is the reference implementation of base.HarnessProvider: chat, the
model catalogue and the health check all live behind that interface, so
swapping opencode for another harness later means adding a module that
implements it and one line in registry.HARNESSES — no UI or route changes.
"""
import logging
from typing import Any

import httpx

from app.api.llm.base import HarnessModel, HarnessProvider, LLMResult
from app.api.llm.errors import (
    LLMProviderError,
    describe_transport_error,
    describe_upstream_error,
)

logger = logging.getLogger(__name__)

# Model/health calls are cheap reads; chat keeps its own long timeout.
_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
# Chat waits longer (a real reply can take a while) but not forever: when the
# harness hangs on a broken model we want a clear error, not a 2-minute stall.
_CHAT_TIMEOUT = httpx.Timeout(90.0, connect=5.0)


def _split_model(model: str | None) -> tuple[str, str] | None:
    """"providerID/modelID" → (providerID, modelID). Model ids may contain
    slashes themselves (deepinfra/meta-llama/…), so split on the first one.
    No slash → not a valid pin, let the harness use its own default."""
    if not model or "/" not in model:
        return None
    provider_id, model_id = model.split("/", 1)
    if not provider_id or not model_id:
        return None
    return provider_id, model_id


def parse_provider_catalogue(data: Any) -> list[HarnessModel]:
    """Flatten opencode's GET /provider (6+ MB of every known provider)
    into generic HarnessModel rows.

    Only *connected* providers are listed — opencode's own verdict that
    credentials work for them (OpenCode Zen, opencode-go, whatever the
    user logs into later), so every option the UI offers actually answers.
    A response without the `connected` field (older opencode) falls back
    to listing everything rather than nothing.
    """
    if not isinstance(data, dict) or not isinstance(data.get("all"), list):
        raise ValueError("Unrecognized /provider response shape")

    connected = data.get("connected")
    connected_set = set(connected) if isinstance(connected, list) else None

    models: list[HarnessModel] = []
    for provider in data["all"]:
        if not isinstance(provider, dict):
            continue
        provider_id = provider.get("id")
        if not provider_id:
            continue
        if connected_set is not None and provider_id not in connected_set:
            continue
        for model_id, model in (provider.get("models") or {}).items():
            if not isinstance(model, dict):
                continue
            limit = model.get("limit") or {}
            capabilities = model.get("capabilities") or {}
            models.append(
                HarnessModel(
                    id=f"{provider_id}/{model_id}",
                    label=model.get("name") or model_id,
                    provider=provider.get("name") or provider_id,
                    context=limit.get("context"),
                    tool_calling=bool(capabilities.get("toolcall")),
                )
            )

    models.sort(key=lambda m: (m.provider.lower(), m.label.lower()))
    return models


class OpenCodeHarnessProvider(HarnessProvider):
    """Sends messages to a headless opencode serve instance via its HTTP API.

    The serve instance handles provider auth and tool use; Aurum only
    passes the conversation and gets the assistant reply back. When a
    model is pinned (llm_settings.harness_model) it's passed per-message,
    so opencode's own default config is never mutated.

    No native tool calling on our side (`supports_tools=False`): opencode
    works from a flattened prompt, so the ChatService uses the
    prompt-embedded JSON action protocol with this backend instead.
    """

    type = "opencode"
    supports_model_choice = True

    def __init__(self, base_url: str = "http://127.0.0.1:4096", model: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResult:
        # Build the user message text from the message history.
        # We send the full history as context, but opencode works with
        # individual prompts — so we flatten the conversation into one prompt.
        prompt = self._build_prompt(messages)
        body: dict[str, Any] = {"parts": [{"type": "text", "text": prompt}]}
        split = _split_model(self.model)
        if split:
            # Per-message override: opencode's config/default stays intact.
            body["model"] = {"providerID": split[0], "modelID": split[1]}

        # 1. Create a session. Transport/HTTP failures are opencode being
        # down or unhappy — LLMProviderError carries a readable detail so
        # the chat route doesn't turn it into an unhandled 500.
        try:
            async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
                session_resp = await client.post(
                    f"{self.base_url}/session",
                    json={},
                )
                session_resp.raise_for_status()
                session_id = session_resp.json()["id"]

                # 2. Send the message
                msg_resp = await client.post(
                    f"{self.base_url}/session/{session_id}/message",
                    json=body,
                )
                msg_resp.raise_for_status()
                data = msg_resp.json()

                # opencode reports a failed model call as HTTP 200 with an
                # `error` object and empty `parts` (rate limit, no funds,
                # region block, ...). Surface it instead of silently returning
                # an empty reply the UI can only show as "no answer".
                if isinstance(data, dict) and data.get("error"):
                    err = data["error"]
                    if isinstance(err, dict):
                        detail = err.get("message") or err.get("name") or str(err)
                    else:
                        detail = str(err)
                    raise LLMProviderError(f"opencode harness: {detail}")

                # 3. Extract text (and reasoning, when present) from the parts
                parts = data.get("parts", [])
                text_parts = [p["text"] for p in parts if p.get("type") == "text"]
                reasoning_parts = [
                    p["text"] for p in parts
                    if p.get("type") in ("reasoning", "thinking") and p.get("text")
                ]

                if not text_parts:
                    # No error object but also no text: the model returned
                    # nothing usable. Don't pretend it was an empty answer.
                    raise LLMProviderError(
                        "opencode harness returned no text "
                        "(model produced an empty reply)"
                    )

                # 4. Clean up session (optional, keeps opencode tidy)
                try:
                    await client.delete(f"{self.base_url}/session/{session_id}")
                except Exception:
                    pass  # not critical

                return LLMResult(
                    text="\n".join(text_parts),
                    reasoning="\n".join(reasoning_parts) or None,
                )
        except httpx.HTTPStatusError as e:
            raise LLMProviderError(
                describe_upstream_error(e.response, self.base_url)
            ) from e
        except httpx.TimeoutException as e:
            raise LLMProviderError(
                f"opencode harness at {self.base_url} timed out — the model "
                "likely hung on a failed call. Check the model/provider is "
                "reachable and has quota."
            ) from e
        except httpx.HTTPError as e:
            raise LLMProviderError(describe_transport_error(e, self.base_url)) from e

    async def list_models(self) -> list[HarnessModel]:
        """GET {base}/provider and flatten the connected providers."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{self.base_url}/provider")
            resp.raise_for_status()
            models = parse_provider_catalogue(resp.json())
        if not models:
            raise ValueError(
                "opencode reports no connected providers — log in / add a "
                "key on the opencode side to see models here"
            )
        return models

    async def health(self) -> str:
        """Create+delete an opencode session — same cheap probe as before."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(f"{self.base_url}/session", json={})
            resp.raise_for_status()
            session_id = resp.json().get("id")
            if session_id:
                await client.delete(f"{self.base_url}/session/{session_id}")
        return f"Harness at {self.base_url} is reachable"

    def _build_prompt(self, messages: list[dict]) -> str:
        """Flatten message history into a single prompt for opencode.

        The system messages become context, user/assistant messages become
        the conversation history.
        """
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[Context]\n{content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            elif role == "tool":
                parts.append(f"[Tool result]\n{content}")
        return "\n\n".join(parts)
