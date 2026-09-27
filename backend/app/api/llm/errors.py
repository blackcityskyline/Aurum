"""Upstream LLM failures — one readable message, no bare 500s.

Every chat driver talks to an external endpoint, and that endpoint's HTTP
answers (bad key, rate limit, outage) are not bugs on Aurum's side: letting
them escape as unhandled exceptions turns each one into a "Internal Server
Error" plus a traceback in the logs, with nothing usable for the user.

So drivers raise LLMProviderError carrying `describe_upstream_error()`'s
message (or `describe_transport_error()` when the endpoint can't even be
reached), and app.api.routes.chat maps it to a 502 whose `detail` the chat
UI shows as-is. The wording lives here so the model-list fetch and the
connectivity test reuse it instead of stringifying the httpx exception.
"""
import json
import logging

import httpx

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """The configured LLM endpoint failed in a way the user can act on
    (wrong key, rate limit, downtime). Never raised for Aurum's own bugs —
    only for answers that came from the provider side."""


# Short phrasing per status — the upstream body may be a JSON blob or an
# HTML error page, so the hint is what actually explains the failure.
_STATUS_HINTS = {
    400: "the endpoint rejected the request",
    401: "invalid or missing API key",
    403: "this API key may not use that model",
    402: "out of credit",
    404: "endpoint or model not found",
    408: "the endpoint timed out",
    413: "request too large for the endpoint",
    429: "rate limited — wait a moment and retry, or pick another model",
    500: "the provider had an internal error",
    502: "the provider is unreachable",
    503: "the provider is temporarily unavailable",
    504: "the provider timed out",
}


def upstream_error_detail(resp: httpx.Response) -> str:
    """The provider's own message, if it sent one we can read.

    OpenAI/OpenRouter shape it as {"error": {"message": …}}, some
    endpoints as {"message": …}; anything else (HTML error page) is dropped
    rather than pasted into the UI wholesale."""
    try:
        body = resp.json()
    except (ValueError, json.JSONDecodeError):
        return ""
    if not isinstance(body, dict):
        return ""
    error = body.get("error")
    if isinstance(error, dict):
        message = error.get("message")
    elif isinstance(error, str):
        message = error
    else:
        message = body.get("message")
    if not isinstance(message, str):
        return ""
    return message.strip()[:300]


def describe_upstream_error(resp: httpx.Response, base_url: str) -> str:
    """`<url> answered HTTP <code>: <hint> — <provider message>`."""
    status = resp.status_code
    hint = _STATUS_HINTS.get(status, "unexpected response")
    message = f"{base_url} answered HTTP {status}: {hint}"
    detail = upstream_error_detail(resp)
    if detail and detail.lower() not in message.lower():
        message = f"{message} — {detail}"
    return message


def describe_transport_error(exc: httpx.HTTPError, base_url: str) -> str:
    """Endpoint never answered (DNS, refused connection, TLS…) — say where
    we were trying to go instead of leaking the httpx repr."""
    if isinstance(exc, httpx.ConnectError):
        reason = "connection refused"
    elif isinstance(exc, httpx.ConnectTimeout):
        reason = "connection timed out"
    elif isinstance(exc, httpx.ReadTimeout):
        reason = "no answer within the timeout"
    else:
        reason = str(exc.__class__.__name__)
    return f"Cannot reach {base_url} ({reason})"


def retry_after_seconds(resp: httpx.Response, default: float = 1.0, cap: float = 3.0) -> float:
    """How long a single retry may sleep after a 429, honouring the
    endpoint's Retry-After but capped so a hostile/absurd value can't hold
    the chat request open."""
    raw = resp.headers.get("retry-after")
    if raw is None:
        return default
    try:
        return max(0.0, min(float(raw), cap))
    except ValueError:
        # HTTP-date form — not worth parsing for a single short retry.
        logger.debug("Unparseable Retry-After header: %r", raw)
        return default
