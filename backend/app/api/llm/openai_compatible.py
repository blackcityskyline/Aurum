"""Generic OpenAI-compatible chat completions provider.

Works with any endpoint that follows the OpenAI /chat/completions format:
OpenRouter, OpenAI, Groq, Ollama, LM Studio, vLLM, and others.
Only base_url, api_key, and model are needed — no provider-specific code.

Implements native tool calling (`supports_tools=True`): the ChatService
hands it the transaction/category/account tool schemas, executes whatever
calls the model returns, and feeds the results back. Models that ignore
tools still work — the ChatService falls back to the prompt-embedded JSON
protocol when a reply arrives with no tool calls.

Endpoint failures (bad key, rate limit, downtime) surface as
errors.LLMProviderError rather than an httpx traceback — see that module.
"""
import asyncio
import json
import logging

import httpx

from app.api.llm.base import AbstractLLMProvider, LLMResult, ToolCall
from app.api.llm.errors import (
    LLMProviderError,
    describe_transport_error,
    describe_upstream_error,
    retry_after_seconds,
)

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(AbstractLLMProvider):
    supports_tools = True

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        model: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ):
        if not base_url:
            raise ValueError(
                "base_url is required for the api backend — add a provider "
                "in Settings → AI"
            )
        if not model:
            raise ValueError(
                "model is required for the api backend — pick one in "
                "Settings → AI"
            )
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def _post(
        self, client: httpx.AsyncClient, payload: dict, headers: dict
    ) -> httpx.Response:
        """POST /chat/completions with the endpoint's failure modes turned
        into LLMProviderError — the chat route maps that to a 502 with a
        readable detail instead of an unhandled 500.

        Exponential backoff on 429: free-tier endpoints rate-limit in
        bursts, so a few pauses with growing delays usually convert a
        failed turn into a successful one instead of an error the user
        has to resend. Honors Retry-After when present, capped so a
        hostile/absurd value can't hold the request open."""
        url = f"{self.base_url}/chat/completions"
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 429 and attempt < max_retries - 1:
                    delay = retry_after_seconds(resp, default=base_delay * (2 ** attempt))
                    logger.warning(
                        "Rate limited (429) on %s, retrying in %.1fs (attempt %d/%d)",
                        self.base_url, delay, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as e:
                raise LLMProviderError(
                    describe_upstream_error(e.response, self.base_url)
                ) from e
            except httpx.HTTPError as e:
                raise LLMProviderError(describe_transport_error(e, self.base_url)) from e

        # Should not reach here, but just in case
        raise LLMProviderError(
            f"Max retries ({max_retries}) exceeded for {self.base_url}"
        )

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResult:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await self._post(client, payload, headers)

        try:
            data = resp.json()
        except ValueError as e:
            raise LLMProviderError(
                f"{self.base_url} returned a non-JSON body"
            ) from e

        choices = data.get("choices") or []
        if not choices:
            logger.warning("Empty choices in response: %s", json.dumps(data)[:500])
            return LLMResult()

        message = choices[0].get("message", {}) or {}
        tool_calls = [
            _parse_tool_call(tc)
            for tc in message.get("tool_calls") or []
            if isinstance(tc, dict)
        ]
        tool_calls = [tc for tc in tool_calls if tc is not None]

        # OpenRouter's reasoning models put the chain-of-thought under
        # `reasoning` (some others use `reasoning_content`).
        reasoning = message.get("reasoning") or message.get("reasoning_content")

        return LLMResult(
            text=message.get("content") or "",
            tool_calls=tool_calls,
            reasoning=reasoning or None,
        )


def _parse_tool_call(raw: dict) -> ToolCall | None:
    """Tolerate the two shapes in the wild: OpenAI's nested
    {function: {name, arguments: "<json string>"}} and endpoints that
    already hand arguments as an object."""
    fn = raw.get("function") if isinstance(raw.get("function"), dict) else raw
    name = fn.get("name")
    if not name:
        logger.warning("Tool call without a name: %s", json.dumps(raw)[:300])
        return None
    args = fn.get("arguments", {})
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            logger.warning("Unparseable tool arguments for %s: %r", name, args[:300])
            args = {"_raw": args}
    if not isinstance(args, dict):
        args = {"_raw": args}
    return ToolCall(id=raw.get("id") or name, name=name, arguments=args)
