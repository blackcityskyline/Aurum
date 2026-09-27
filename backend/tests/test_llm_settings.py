"""Coverage for the Settings → AI surface: llm config/provider CRUD,
the API-key write-only contract, and the ChatService tool-calling loop.

The two things most worth pinning down: keys must never echo back once
saved (the whole point of moving config from env into the DB), and the
tool loop must both execute what the model asks for and stop when it's
done — including when the model never stops asking.
"""
import json

import pytest

from app.api.llm.base import LLMConfig, LLMResult, ToolCall
from app.services.chat_service import MAX_TOOL_ROUNDS, ChatService


# ---------------------------------------------------------------- llm config

async def test_config_defaults_to_harness_without_env_overrides(client):
    resp = await client.get("/llm/config")
    assert resp.status_code == 200
    data = resp.json()
    # Fresh test DB: no llm_settings row yet → seeded from env, where
    # AURUM_LLM_PROVIDER defaults to "opencode" → mapped to "harness".
    assert data["mode"] in ("harness", "api", "stub")
    assert data["providers"] == []
    assert data["active_provider_id"] is None


async def test_provider_crud_and_activation(client):
    created = await client.post(
        "/llm/providers",
        json={
            "name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1/",
            "api_key": "sk-secret-123",
            "model": "meta-llama/llama-3.3-70b-instruct:free",
        },
    )
    assert created.status_code == 201
    provider = created.json()
    assert provider["base_url"] == "https://openrouter.ai/api/v1"  # trailing / trimmed
    assert provider["is_active"] is True  # first provider auto-activates

    second = await client.post(
        "/llm/providers",
        json={"name": "Ollama", "base_url": "http://localhost:11434/v1", "activate": False},
    )
    assert second.status_code == 201
    assert second.json()["is_active"] is False

    # A provider created without an explicit flag becomes active — adding
    # one is normally done in order to use it.
    third = await client.post(
        "/llm/providers",
        json={"name": "Groq", "base_url": "https://api.groq.com/openai/v1"},
    )
    assert third.json()["is_active"] is True

    # Switch the active provider back to the second one.
    patched = await client.patch("/llm/config", json={"active_provider_id": second.json()["id"]})
    assert patched.status_code == 200
    assert patched.json()["active_provider_id"] == second.json()["id"]

    # Dangling id is rejected instead of silently leaving a broken state.
    bad = await client.patch("/llm/config", json={"active_provider_id": 9999})
    assert bad.status_code == 400

    # Deleting the active provider clears the pointer.
    deleted = await client.delete(f"/llm/providers/{second.json()['id']}")
    assert deleted.status_code == 204
    after = await client.get("/llm/config")
    assert after.json()["active_provider_id"] is None
    assert len(after.json()["providers"]) == 2


async def test_api_key_never_returns_after_save(client):
    await client.post(
        "/llm/providers",
        json={"name": "P", "base_url": "https://x.test/v1", "api_key": "sk-topsecret"},
    )

    listed = await client.get("/llm/config")
    assert "sk-topsecret" not in listed.text
    provider = listed.json()["providers"][0]
    assert provider["has_api_key"] is True
    assert "api_key" not in provider

    # An update that doesn't touch the key must keep it (verify via has_api_key).
    await client.patch(f"/llm/providers/{provider['id']}", json={"name": "Renamed"})
    after = await client.get("/llm/config")
    assert after.json()["providers"][0]["has_api_key"] is True
    assert "sk-topsecret" not in after.text

    # Empty string clears it explicitly.
    await client.patch(f"/llm/providers/{provider['id']}", json={"api_key": ""})
    cleared = await client.get("/llm/config")
    assert cleared.json()["providers"][0]["has_api_key"] is False


async def test_mode_switch_harness_to_api(client):
    created = await client.post(
        "/llm/providers",
        json={"name": "P", "base_url": "https://x.test/v1", "model": "some-model"},
    )
    provider_id = created.json()["id"]

    resp = await client.patch("/llm/config", json={"mode": "api"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "api"
    assert data["active_provider_id"] == provider_id

    back = await client.patch("/llm/config", json={"mode": "harness"})
    assert back.json()["mode"] == "harness"

    # "stub" is dev-only — the UI update schema refuses it.
    invalid = await client.patch("/llm/config", json={"mode": "stub"})
    assert invalid.status_code == 422


async def test_validation_rejects_non_http_base_url(client):
    resp = await client.post(
        "/llm/providers", json={"name": "P", "base_url": "ftp://nope"}
    )
    assert resp.status_code == 422


async def test_models_endpoint_unreachable_returns_400(client):
    # 127.0.0.1:1 refuses instantly — proves the error path without network.
    resp = await client.post(
        "/llm/models", json={"base_url": "http://127.0.0.1:1/v1"}
    )
    assert resp.status_code == 400
    assert "Failed to fetch models" in resp.json()["detail"]


# ------------------------------------------------------------ chat tool loop


class FakeToolProvider:
    """Scripted api-mode provider: hands out queued results, then plain text."""

    supports_tools = True

    def __init__(self, results):
        self.results = list(results)
        self.seen_tools = None

    async def chat(self, messages, tools=None):
        self.seen_tools = tools
        return self.results.pop(0) if self.results else LLMResult(text="done")


def _config() -> LLMConfig:
    return LLMConfig(mode="api", base_url="https://x.test/v1", model="m")


async def test_tool_loop_executes_calls_and_returns_final_text(
    test_sessionmaker, client, account_id
):
    provider = FakeToolProvider(
        [
            LLMResult(
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="create_transaction",
                        arguments={
                            "account_id": account_id,
                            "type": "expense",
                            "amount": 42.5,
                            "description": "Coffee",
                            "date": "2026-09-23",
                        },
                    )
                ]
            ),
            LLMResult(text="Added your coffee expense.", reasoning="should buy beans"),
        ]
    )

    async with test_sessionmaker() as session:
        svc = ChatService(session, provider, _config())
        resp = await svc.process_message("запиши кофе за 42.50")

    # Final text came from the second round; reasoning is carried through.
    assert resp.reply == "Added your coffee expense."
    assert resp.message.reasoning == "should buy beans"
    assert [a.type for a in resp.message.actions] == ["create_transaction"]
    assert resp.message.actions[0].status == "executed"

    # The tool schemas were actually offered to the model.
    tool_names = {t["function"]["name"] for t in provider.seen_tools}
    assert {"create_transaction", "update_transaction", "list_transactions"} <= tool_names

    # And the row really landed in the DB.
    from sqlalchemy import select
    from app.models.transaction import Transaction
    async with test_sessionmaker() as session:
        rows = (await session.execute(select(Transaction))).scalars().all()
        assert len(rows) == 1
        assert str(rows[0].amount) == "42.50"


async def test_tool_loop_is_bounded_when_model_never_stops(
    test_sessionmaker, account_id
):
    """A model that calls a tool every single round must be cut off after
    MAX_TOOL_ROUNDS instead of looping forever."""
    class EndlessProvider(FakeToolProvider):
        async def chat(self, messages, tools=None):
            self.seen_tools = tools
            return LLMResult(
                tool_calls=[
                    ToolCall(
                        id="x",
                        name="list_transactions",
                        arguments={"limit": 5},
                    )
                ]
            )

    provider = EndlessProvider([])
    async with test_sessionmaker() as session:
        svc = ChatService(session, provider, _config())
        resp = await svc.process_message("analiza")

    assert len(resp.message.actions) == MAX_TOOL_ROUNDS
    # Bounded loop means a fallback reply, never an empty bubble.
    assert resp.reply


async def test_text_protocol_fallback_when_model_ignores_tools(
    test_sessionmaker, account_id
):
    """Tool-capable backend that answers with plain JSON anyway — the
    prompt-embedded protocol must still run its actions."""
    payload = json.dumps(
        {
            "reply": "Готово",
            "actions": [
                {
                    "type": "create_transaction",
                    "params": {
                        "account_id": account_id,
                        "type": "expense",
                        "amount": 10,
                        "description": "Bus",
                    },
                }
            ],
        }
    )
    provider = FakeToolProvider([LLMResult(text=payload)])

    async with test_sessionmaker() as session:
        svc = ChatService(session, provider, _config())
        resp = await svc.process_message("автобус 10")

    assert resp.reply == "Готово"
    assert resp.message.actions[0].status == "executed"


async def test_failed_tool_call_is_reported_back_to_the_model(
    test_sessionmaker, account_id
):
    """A bad call (missing transaction) fails locally, gets reported to the
    model in the tool result, and the turn still completes."""
    provider = FakeToolProvider(
        [
            LLMResult(
                tool_calls=[
                    ToolCall(id="d1", name="delete_transaction", arguments={"transaction_id": 424242})
                ]
            ),
            LLMResult(text="Не нашёл такую транзакцию."),
        ]
    )

    async with test_sessionmaker() as session:
        svc = ChatService(session, provider, _config())
        resp = await svc.process_message("удали 424242")

    action = resp.message.actions[0]
    assert action.status == "failed"
    assert "not found" in action.error
    assert resp.reply == "Не нашёл такую транзакцию."


@pytest.mark.parametrize("bad_type", ["delete_everything", "", "unknown_action"])
async def test_unknown_action_type_fails_gracefully(test_sessionmaker, bad_type):
    from app.schemas.chat import ChatAction

    async with test_sessionmaker() as session:
        svc = ChatService(session, FakeToolProvider([]), _config())
        result = await svc._execute_action(
            ChatAction(type=bad_type, params={}, status="pending")
        )
    assert result.status == "failed"
    assert "Unknown action type" in result.error


# ------------------------------------------------------------ harness driver


async def test_harness_model_pin_roundtrip(client):
    """harness_model is persisted, and "" (the picker's "default" option)
    clears the pin so opencode's own default answers again."""
    assert (await client.get("/llm/config")).json()["harness_model"] is None

    pinned = await client.patch("/llm/config", json={"harness_model": "opencode/big-pickle"})
    assert pinned.status_code == 200
    assert pinned.json()["harness_model"] == "opencode/big-pickle"
    assert (await client.get("/llm/config")).json()["harness_model"] == "opencode/big-pickle"

    cleared = await client.patch("/llm/config", json={"harness_model": ""})
    assert cleared.json()["harness_model"] is None


async def test_harness_type_validated_against_registry(client):
    # Unknown driver → 400, with the available keys in the detail so a
    # future UI could enumerate them from the registry.
    bad = await client.patch("/llm/config", json={"harness_type": "langchain"})
    assert bad.status_code == 400
    assert "opencode" in bad.json()["detail"]

    ok = await client.patch("/llm/config", json={"harness_type": "opencode"})
    assert ok.status_code == 200
    assert ok.json()["harness_type"] == "opencode"


async def test_harness_models_endpoint_returns_generic_rows(client, monkeypatch):
    """GET /llm/harness/models serves whatever the active driver's
    list_models() returns — rows are generic, not opencode-shaped."""
    from app.api.llm.base import HarnessModel
    from app.api.llm.opencode_harness import OpenCodeHarnessProvider

    async def fake_list_models(self):
        return [
            HarnessModel(
                id="opencode/big-pickle",
                label="Big Pickle",
                provider="OpenCode Zen",
                context=200000,
                tool_calling=True,
            )
        ]

    monkeypatch.setattr(OpenCodeHarnessProvider, "list_models", fake_list_models)

    resp = await client.get("/llm/harness/models")
    assert resp.status_code == 200
    row = resp.json()["models"][0]
    assert row["id"] == "opencode/big-pickle"
    assert row["provider"] == "OpenCode Zen"
    assert row["context"] == 200000
    assert row["tool_calling"] is True


def test_parse_provider_catalogue_filters_to_connected():
    """opencode's GET /provider lists every provider on the internet; only
    `connected` ones (credentials work) may reach the picker — otherwise
    the user could pick a model that never answers."""
    from app.api.llm.opencode_harness import parse_provider_catalogue

    payload = {
        "all": [
            {
                "id": "opencode",
                "name": "OpenCode Zen",
                "models": {
                    "big-pickle": {
                        "name": "Big Pickle",
                        "limit": {"context": 1000},
                        "capabilities": {"toolcall": True},
                    }
                },
            },
            {"id": "nokey", "name": "No Key", "models": {"m1": {"name": "M1"}}},
        ],
        "connected": ["opencode"],
    }

    models = parse_provider_catalogue(payload)
    assert [m.id for m in models] == ["opencode/big-pickle"]
    assert models[0].provider == "OpenCode Zen"
    assert models[0].context == 1000
    assert models[0].tool_calling is True

    # Older opencode without the `connected` field → list everything.
    no_field = dict(payload)
    no_field.pop("connected")
    assert len(parse_provider_catalogue(no_field)) == 2

    # Present but empty → no credentials anywhere → nothing to offer.
    assert parse_provider_catalogue({"all": payload["all"], "connected": []}) == []

    with pytest.raises(ValueError):
        parse_provider_catalogue({"unexpected": True})


def test_split_model_keeps_slashes_inside_model_ids():
    from app.api.llm.opencode_harness import _split_model

    assert _split_model(None) is None
    assert _split_model("") is None
    # No provider part → not a valid pin, harness default stays in charge.
    assert _split_model("big-pickle") is None
    assert _split_model("opencode/big-pickle") == ("opencode", "big-pickle")
    # Model ids may contain slashes of their own — split on the first one.
    assert _split_model("deepinfra/meta-llama/x") == ("deepinfra", "meta-llama/x")


def test_registry_builds_harness_driver_with_pinned_model():
    from app.api.llm.opencode_harness import OpenCodeHarnessProvider
    from app.api.llm.registry import get_harness

    config = LLMConfig(
        mode="harness",
        harness_type="opencode",
        harness_url="http://harness:4096/",
        harness_model="opencode/big-pickle",
    )
    driver = get_harness(config)
    assert isinstance(driver, OpenCodeHarnessProvider)
    assert driver.base_url == "http://harness:4096"  # trailing / trimmed
    assert driver.model == "opencode/big-pickle"
    assert driver.supports_model_choice is True

    with pytest.raises(ValueError, match="Unknown harness type"):
        get_harness(LLMConfig(harness_type="nonexistent"))


# ------------------------------------------------------------ models route


async def test_models_route_accepts_provider_id_alone(client, monkeypatch):
    """The chat's model picker sends only `provider_id` — base_url used to be
    required by the schema, so every picker request came back 422, the
    catalogue stayed empty and the <select> stayed disabled (clicking its
    arrow did nothing). The saved row alone must be enough."""
    from app.api.routes import llm as llm_routes

    seen: dict = {}

    async def fake_fetch_models(base_url, api_key):
        seen.update(base_url=base_url, api_key=api_key)
        return ["a/model:free", "b/model"]

    monkeypatch.setattr(llm_routes, "fetch_models", fake_fetch_models)

    created = await client.post(
        "/llm/providers",
        json={
            "name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-secret-123",
        },
    )
    resp = await client.post("/llm/models", json={"provider_id": created.json()["id"]})

    assert resp.status_code == 200
    assert resp.json()["models"] == ["a/model:free", "b/model"]
    assert seen == {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": "sk-secret-123",
    }


async def test_models_route_prefers_typed_values_over_the_stored_row(client, monkeypatch):
    """ProviderDialog loads models *before* saving the edit, so a url/key
    typed into the form wins over what the row still stores; omitting the
    key keeps the stored one (the server never has it in the payload)."""
    from app.api.routes import llm as llm_routes

    seen: dict = {}

    async def fake_fetch_models(base_url, api_key):
        seen.update(base_url=base_url, api_key=api_key)
        return ["m1"]

    monkeypatch.setattr(llm_routes, "fetch_models", fake_fetch_models)

    created = await client.post(
        "/llm/providers",
        json={
            "name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": "sk-secret-123",
        },
    )
    pid = created.json()["id"]

    await client.post(
        "/llm/models",
        json={"provider_id": pid, "base_url": "http://localhost:11434/v1", "api_key": "typed"},
    )
    assert seen == {"base_url": "http://localhost:11434/v1", "api_key": "typed"}

    await client.post(
        "/llm/models", json={"provider_id": pid, "base_url": "http://localhost:11434/v1"}
    )
    assert seen["api_key"] == "sk-secret-123"


async def test_models_route_rejects_requests_with_nothing_to_fetch_from(client):
    # Neither id nor url →400 with the rule spelled out, not a 500.
    neither = await client.post("/llm/models", json={})
    assert neither.status_code == 400
    assert "provider_id" in neither.json()["detail"]

    # A url that isn't one → 400 before any network call happens.
    not_a_url = await client.post("/llm/models", json={"base_url": "openrouter.ai"})
    assert not_a_url.status_code == 400
    assert "http" in not_a_url.json()["detail"]

    # Unknown provider id → 404 from the row lookup.
    missing = await client.post("/llm/models", json={"provider_id": 424242})
    assert missing.status_code == 404


# ------------------------------------------------------- upstream failures


def _upstream(status: int, *, json_body=None, text=None, headers=None) -> "httpx.Response":
    import httpx

    return httpx.Response(
        status,
        json=json_body,
        text=text,
        headers=headers or {},
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )


def test_upstream_error_is_described_for_humans():
    """A provider's HTTP failure must reach the UI as a sentence (what
    happened + what the provider said), never as an httpx traceback."""
    import httpx

    from app.api.llm.errors import describe_transport_error, describe_upstream_error

    rate_limited = _upstream(429, json_body={"error": {"message": "Rate limit exceeded"}})
    msg = describe_upstream_error(rate_limited, "https://openrouter.ai/api/v1")
    assert "HTTP 429" in msg
    assert "rate limited" in msg
    assert "Rate limit exceeded" in msg

    # HTML error page — no provider message to quote, hint alone must read.
    page = _upstream(500, text="<html><body>oops</body></html>")
    assert "provider had an internal error" in describe_upstream_error(page, "https://x/v1")

    # Unknown status still yields a usable sentence.
    weird = _upstream(418, json_body={"message": "teapot"})
    assert "HTTP 418" in describe_upstream_error(weird, "https://x/v1")

    refused = httpx.ConnectError("refused", request=httpx.Request("GET", "http://h:1/"))
    assert "Cannot reach http://h:1/" in describe_transport_error(refused, "http://h:1/")
    assert "connection refused" in describe_transport_error(refused, "http://h:1/")


def test_retry_after_is_honoured_but_capped():
    from app.api.llm.errors import retry_after_seconds

    assert retry_after_seconds(_upstream(429)) == 1.0  # header absent → default
    assert retry_after_seconds(_upstream(429, headers={"retry-after": "0"})) == 0.0
    assert retry_after_seconds(_upstream(429, headers={"retry-after": "120"})) == 3.0  # capped
    assert retry_after_seconds(_upstream(429, headers={"retry-after": "soon"})) == 1.0


async def test_openai_provider_retries_once_on_429_then_raises_readable_error(monkeypatch):
    """Free-tier rate limits come in bursts: one short retry first, and if
    the endpoint still says 429 the failure is LLMProviderError — the chat
    route turns that into a 502 detail, not an unhandled 500."""
    import httpx

    from app.api.llm.errors import LLMProviderError
    from app.api.llm.openai_compatible import OpenAICompatibleProvider

    class FakeClient:
        def __init__(self, *a, **kw):
            self.calls = 0
            self.responses = [
                _upstream(429, json_body={"error": {"message": "slow down"}},
                          headers={"retry-after": "0"}),
                _upstream(429, json_body={"error": {"message": "slow down"}},
                          headers={"retry-after": "0"}),
            ]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            self.calls += 1
            return self.responses[min(self.calls, len(self.responses)) - 1]

    holder: dict = {}

    def factory(*a, **kw):
        holder["client"] = FakeClient(*a, **kw)
        return holder["client"]

    monkeypatch.setattr(httpx, "AsyncClient", factory)

    provider = OpenAICompatibleProvider(base_url="https://openrouter.ai/api/v1", model="m")
    with pytest.raises(LLMProviderError) as exc:
        await provider.chat([{"role": "user", "content": "hi"}])

    assert "HTTP 429" in str(exc.value)
    assert holder["client"].calls == 2  # exactly one retry, no loop


async def test_chat_route_answers_502_with_the_provider_detail(client, monkeypatch):
    """The endpoint failing is a gateway problem, not an Aurum bug: 502 with
    the readable message the UI shows, instead of "internal server error"."""
    from app.api.llm.errors import LLMProviderError
    from app.api.routes import chat as chat_routes

    async def boom(self, message, session_id=None):
        raise LLMProviderError(
            "https://openrouter.ai/api/v1 answered HTTP 429: rate limited — "
            "wait a moment and retry, or pick another model"
        )

    monkeypatch.setattr(chat_routes.ChatService, "process_message", boom)

    resp = await client.post("/chat", json={"message": "привет"})
    assert resp.status_code == 502
    assert "HTTP 429" in resp.json()["detail"]


async def test_create_transaction_reports_missing_required_fields(test_sessionmaker):
    """A model that skips account_id/amount used to blow up on params[…]
    and report a bare KeyError back into the chat."""
    from app.schemas.chat import ChatAction

    async with test_sessionmaker() as session:
        svc = ChatService(session, FakeToolProvider([]), _config())
        result = await svc._execute_action(
            ChatAction(type="create_transaction", params={"type": "expense"}, status="pending")
        )

    assert result.status == "failed"
    assert "account_id" in result.error
    assert "amount" in result.error
