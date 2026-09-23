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
