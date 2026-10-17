"""OpenCode harness driver — calls a running opencode serve instance.

This is the reference implementation of base.HarnessProvider: chat, the
model catalogue and the health check all all live behind that interface, so
swapping opencode for another harness later means adding a module that
implements it and one line in registry.HARNESSES — no UI or route changes.

Targets the opencode 2.x HTTP API: everything lives under ``/api``, a chat
turn is asynchronous (``POST /api/session/{id}/prompt`` accepts the prompt and
the reply is read back from ``GET /api/session/{id}/message``), and requests
are Basic-authenticated with username ``opencode`` plus the serve instance's
server password (``OPENCODE_SERVER_PASSWORD``).
"""
import asyncio
import logging
import os
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
# Chat waits for an async generation to finish: a real reply can take a while
# but not forever — when the harness hangs on a broken model we want a clear
# error, not an indefinite stall.
_CHAT_TIMEOUT = httpx.Timeout(90.0, connect=5.0)
# How often we poll GET /message for the assistant reply.
_POLL_INTERVAL_S = 1.5


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
    """Kept for compatibility: opencode 1.x exposed a model catalogue on
    GET /provider; 2.x does not (providers became packages that resolve models
    upstream). chat() no longer depends on this — it is only referenced by
    tests/legacy callers."""
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
    passes the conversation and gets the assistant reply back. When a model
    is pinned (llm_settings.harness_model) it's set on the session at
    creation, so opencode's own default config is never mutated.

    No native tool calling on our side (`supports_tools=False`): opencode
    works from a flattened prompt, so the ChatService uses the
    prompt-embedded JSON action protocol with this backend instead.
    """

    type = "opencode"
    supports_model_choice = True

    def __init__(self, base_url: str = "http://127.0.0.1:4096", model: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        # opencode 2.x serve requires Basic auth (user "opencode" + server
        # password). The password is infra plumbing, not a user-facing model
        # setting, so it comes from the environment rather than the DB.
        password = os.environ.get("AURUM_OPENCODE_SERVER_PASSWORD")
        self._auth = httpx.BasicAuth("opencode", password) if password else None

    def _client(self, timeout: httpx.Timeout) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url, auth=self._auth, timeout=timeout
        )

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResult:
        # Flatten the conversation into a single prompt for opencode.
        prompt = self._build_prompt(messages)

        try:
            async with self._client(_CHAT_TIMEOUT) as client:
                # 1. Create a session (optionally pin a model).
                create_body: dict[str, Any] = {}
                split = _split_model(self.model)
                if split:
                    create_body["model"] = {
                        "providerID": split[0],
                        "modelID": split[1],
                    }
                session_resp = await client.post("/api/session", json=create_body)
                session_resp.raise_for_status()
                session_id = session_resp.json()["data"]["id"]

                try:
                    # 2. Accept the prompt (async — the reply is polled below).
                    prompt_resp = await client.post(
                        f"/api/session/{session_id}/prompt", json={"text": prompt}
                    )
                    prompt_resp.raise_for_status()

                    # 3. Poll messages until the assistant reply completes.
                    return await self._await_reply(client, session_id)
                finally:
                    # 4. Clean up the session (best-effort, keeps opencode tidy).
                    try:
                        await client.delete(f"/api/session/{session_id}")
                    except Exception:
                        pass
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

    async def _await_reply(
        self, client: httpx.AsyncClient, session_id: str
    ) -> LLMResult:
        """Poll GET /message until the assistant message completes (or fails)."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (_CHAT_TIMEOUT.read or 90.0)
        while True:
            resp = await client.get(f"/api/session/{session_id}/message")
            resp.raise_for_status()
            data = resp.json()
            msgs = data.get("data", data) if isinstance(data, dict) else data
            msgs = msgs if isinstance(msgs, list) else []

            text_parts: list[str] = []
            reasoning_parts: list[str] = []
            for m in msgs:
                if not isinstance(m, dict):
                    continue
                # An explicit per-message error (rate limit, no funds, ...).
                if m.get("type") == "assistant" and m.get("error"):
                    err = m["error"]
                    detail = (
                        err.get("message") or err.get("name") or str(err)
                        if isinstance(err, dict)
                        else str(err)
                    )
                    raise LLMProviderError(f"opencode harness: {detail}")
                if m.get("type") != "assistant":
                    continue
                for part in m.get("content") or []:
                    if not isinstance(part, dict):
                        continue
                    ptype = part.get("type")
                    if ptype == "text" and part.get("text"):
                        text_parts.append(part["text"])
                    elif ptype in ("reasoning", "thinking") and part.get("text"):
                        reasoning_parts.append(part["text"])
                # A completed assistant turn is our answer.
                if (m.get("time") or {}).get("completed") and text_parts:
                    return LLMResult(
                        text="\n".join(text_parts),
                        reasoning="\n".join(reasoning_parts) or None,
                    )

            if loop.time() >= deadline:
                if text_parts:
                    # We have text but never saw a completion marker — return
                    # it rather than fail; better a slightly early answer.
                    return LLMResult(
                        text="\n".join(text_parts),
                        reasoning="\n".join(reasoning_parts) or None,
                    )
                raise LLMProviderError(
                    "opencode harness returned no reply before timeout "
                    "(model produced no text — it may be rate-limited or out "
                    "of quota)"
                )
            await asyncio.sleep(_POLL_INTERVAL_S)

    async def list_models(self) -> list[HarnessModel]:
        """opencode 2.x no longer exposes a model catalogue over HTTP —
        providers are packages that resolve models upstream. The model is set
        on the opencode side (or pinned manually); there's nothing to list."""
        raise ValueError(
            "opencode 2.x doesn't expose a model list over its API — leave the "
            "model blank to use opencode's default, or set it manually on the "
            "opencode side"
        )

    async def health(self) -> str:
        """Create+delete an opencode session — same cheap probe as before."""
        async with self._client(_TIMEOUT) as client:
            resp = await client.post("/api/session", json={})
            resp.raise_for_status()
            session_id = (resp.json().get("data") or {}).get("id")
            if session_id:
                await client.delete(f"/api/session/{session_id}")
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
