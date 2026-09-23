"""Chat service — orchestrates context building, LLM calls, and action execution."""
import json
import logging
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.llm import LLMConfig
from app.api.llm.base import LLMResult, ToolCall
from app.core.config import get_settings
from app.models.account import Account
from app.models.category import Category
from app.models.chat import ChatMessage, ChatSession
from app.models.transaction import Transaction
from app.schemas.chat import ChatAction, ChatMessageRead, ChatResponse

logger = logging.getLogger(__name__)

# How many tool round-trips one user turn may spend before we stop asking
# the model and report what got done. Cheap insurance against a model that
# keeps calling tools (or one that answers with text after every single
# call) holding the HTTP request open indefinitely.
MAX_TOOL_ROUNDS = 4

# Tool schemas handed to OpenAI-compatible endpoints (Settings → AI, api
# mode). Deliberately a short, routine-ops list — add/update/delete a
# transaction, the two catalog writes the assistant may need while doing
# so, and a period read for spending analysis. Anything fancier belongs in
# the app's own pages, not in a chat side effect.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_transaction",
            "description": "Add an income, expense, or transfer transaction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {"type": "integer", "description": "Target account id"},
                    "type": {"type": "string", "enum": ["income", "expense", "transfer"]},
                    "amount": {"type": "number", "description": "Positive amount"},
                    "description": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD, defaults to today"},
                    "category_id": {"type": "integer"},
                },
                "required": ["account_id", "type", "amount", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_transaction",
            "description": "Change fields of an existing transaction; omit fields to leave them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "integer"},
                    "account_id": {"type": "integer"},
                    "type": {"type": "string", "enum": ["income", "expense", "transfer"]},
                    "amount": {"type": "number"},
                    "description": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "category_id": {"type": "integer"},
                },
                "required": ["transaction_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_transaction",
            "description": "Remove a transaction by id.",
            "parameters": {
                "type": "object",
                "properties": {"transaction_id": {"type": "integer"}},
                "required": ["transaction_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_category",
            "description": "Add a category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "kind": {"type": "string", "enum": ["income", "expense"]},
                },
                "required": ["name", "kind"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_account",
            "description": "Add an account.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["checking", "debit_card", "savings", "credit_card",
                                 "cash", "investment", "other"],
                    },
                    "currency": {"type": "string", "description": "ISO 4217 code"},
                },
                "required": ["name", "type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_transactions",
            "description": "Read transactions for a period to analyze spending.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date_from": {"type": "string", "description": "YYYY-MM-DD inclusive"},
                    "date_to": {"type": "string", "description": "YYYY-MM-DD inclusive"},
                    "account_id": {"type": "integer"},
                    "category_id": {"type": "integer"},
                    "limit": {"type": "integer", "description": "Max rows, default 50"},
                },
            },
        },
    },
]


def _assistant_tool_calls_message(result: LLMResult) -> dict:
    """The OpenAI-format assistant turn that *requests* the tool calls —
    required in the conversation before the tool results, or every
    endpoint rejects the follow-up request."""
    return {
        "role": "assistant",
        "content": result.text or None,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in result.tool_calls
        ],
    }


def _tool_result_message(call: ToolCall, action: ChatAction) -> dict:
    """Tool result for the model: outcome + error if any, so a failed call
    gets a chance to be corrected or explained instead of silently lost."""
    payload = {
        "status": action.status,
        "result": action.result,
        "error": action.error,
    }
    return {
        "role": "tool",
        "tool_call_id": call.id,
        "content": json.dumps(payload, ensure_ascii=False),
    }

SYSTEM_PROMPT = """You are Aurum's financial assistant. You can read the user's
financial data (accounts, transactions, budgets, categories) and help them manage
their personal finances.

Available tools (use them — don't invent JSON by hand when tools are offered):
- create_transaction: add a transaction
- update_transaction: change an existing transaction (only the given fields)
- delete_transaction: remove a transaction
- create_category / create_account: add a category or account
- list_transactions: read transactions for a period (use this to analyze spending)

Keep it simple: the user asks routine things (log a purchase, fix an amount,
delete a duplicate, compare spending over a period). Confirm what you did in
one or two short sentences, in the same language the user writes in.

If no tools are available (some backends answer in one shot), respond ONLY with
a single JSON object (no markdown fences, no text before or after it):
- "reply": a natural language response to the user
- "actions": a list of {"type", "params"} objects using the same action names
  as the tools above.
If no actions are needed, return {"reply": "...", "actions": []}."""


class ChatService:
    def __init__(self, session: AsyncSession, provider, config: LLMConfig):
        self.session = session
        self.provider = provider
        self.config = config

    async def process_message(
        self, user_message: str, session_id: int | None = None
    ) -> ChatResponse:
        # 1. Find or create session
        if session_id is not None:
            chat_session = await self.session.get(ChatSession, session_id)
            if chat_session is None:
                raise ValueError(f"Chat session {session_id} not found")
        else:
            chat_session = ChatSession(title=user_message[:100])
            self.session.add(chat_session)
            await self.session.flush()

        # 2. Save user message
        user_msg = ChatMessage(
            session_id=chat_session.id,
            role="user",
            content=user_message,
        )
        self.session.add(user_msg)
        await self.session.flush()

        # 3. Build context and call LLM
        history = await self._get_history(chat_session.id)
        financial_ctx = await self._build_financial_context()

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"Financial context:\n{financial_ctx}"},
            *history,
            {"role": "user", "content": user_message},
        ]

        reply_text, reasoning, actions = await self._call_llm(messages)

        # 5. Execute actions — only the ones still pending. The tool loop
        # in _call_with_tools runs its calls inline (the model needs the
        # result fed back to continue), so re-executing those here would
        # duplicate every write; text-protocol actions arrive untouched.
        executed_actions = []
        for action in actions:
            if action.status == "pending":
                action = await self._execute_action(action)
            executed_actions.append(action)

        # 6. Save assistant message. Commit is what actually persists both the
        # chat rows *and* any transaction created in step 5 — if it raises, the
        # whole request fails and nothing is half-saved.
        assistant_msg = ChatMessage(
            session_id=chat_session.id,
            role="assistant",
            content=reply_text,
            reasoning=reasoning,
            actions_json=json.dumps([a.model_dump() for a in executed_actions]),
        )
        self.session.add(assistant_msg)
        try:
            await self.session.commit()
        except Exception:
            logger.exception("Failed to commit chat response; rolling back")
            await self.session.rollback()
            raise

        return ChatResponse(
            session_id=chat_session.id,
            message=ChatMessageRead(
                id=assistant_msg.id,
                role="assistant",
                content=reply_text,
                reasoning=reasoning,
                actions=executed_actions,
                created_at=assistant_msg.created_at,
            ),
            reply=reply_text,
        )

    async def _get_history(self, session_id: int, limit: int = 20) -> list[dict]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        messages = list(result.scalars().all())
        messages.reverse()
        return [{"role": m.role, "content": m.content} for m in messages]

    async def _build_financial_context(self) -> str:
        lines: list[str] = []

        # Account balances
        accounts_stmt = select(Account).where(Account.is_archived == False)
        accounts = (await self.session.execute(accounts_stmt)).scalars().all()
        if accounts:
            lines.append("Accounts:")
            for a in accounts:
                lines.append(f"  - {a.name} ({a.type.value}, {a.currency})")

        # Recent transactions (last 10)
        recent_stmt = (
            select(Transaction)
            .order_by(Transaction.date.desc())
            .limit(10)
        )
        recent = (await self.session.execute(recent_stmt)).scalars().all()
        if recent:
            lines.append("Recent transactions:")
            for t in recent:
                lines.append(
                    f"  - {t.date}: {t.type.value} {t.amount} "
                    f"(category_id={t.category_id}, desc={t.description or ''})"
                )

        # Categories
        cats_stmt = select(Category).order_by(Category.sort_order)
        cats = (await self.session.execute(cats_stmt)).scalars().all()
        if cats:
            lines.append("Categories: " + ", ".join(
                f"{c.name}({c.kind.value}, id={c.id})" for c in cats
            ))

        if not lines:
            return "No financial data available yet."

        return "\n".join(lines)

    async def _call_llm(
        self, messages: list[dict]
    ) -> tuple[str, str | None, list[ChatAction]]:
        """One user turn against the configured backend, returning
        (reply, reasoning, actions).

        Two protocols, picked by what the backend supports:

        * Tool-capable (api mode): native OpenAI tool calling — call the
          model, execute its tool calls, feed the results back, repeat
          until it answers with plain text. Bounded by MAX_TOOL_ROUNDS so
          a looping model can't hold the request open forever.
        * Not tool-capable (harness/stub): the prompt-embedded JSON
          protocol — the model answers with {"reply", "actions"} in one
          shot and we execute immediately (also the fallback below when a
          tool-capable model just replies in text).
        """
        if self.provider.supports_tools:
            return await self._call_with_tools(messages)

        result = await self.provider.chat(messages, tools=None)
        reply, actions = self._parse_response(result.text)
        return reply, result.reasoning, actions

    async def _call_with_tools(
        self, messages: list[dict]
    ) -> tuple[str, str | None, list[ChatAction]]:
        executed: list[ChatAction] = []
        reasonings: list[str] = []
        convo = list(messages)

        for _ in range(MAX_TOOL_ROUNDS):
            result = await self.provider.chat(convo, tools=TOOLS)
            if result.reasoning:
                reasonings.append(result.reasoning)

            if not result.tool_calls:
                # Final answer (or a text-protocol reply — parse it too, so
                # models that ignore tools still get their actions run).
                if executed and not result.tool_calls:
                    # Already ran tools; a bare text reply is the wrap-up.
                    reply = result.text or self._actions_summary(executed)
                    return reply, "\n\n".join(reasonings) or None, executed
                reply, actions = self._parse_response(result.text)
                return reply, "\n".join(reasonings) or None, executed + actions

            # Record the model's intent, then execute and report back.
            convo.append(_assistant_tool_calls_message(result))
            for call in result.tool_calls:
                action = ChatAction(
                    type=call.name, params=call.arguments, status="pending"
                )
                executed.append(await self._execute_action(action))
                convo.append(_tool_result_message(call, executed[-1]))

        # Ran out of rounds — hand back whatever the last state is instead
        # of hanging: the executed actions are already done and durable.
        reply = self._actions_summary(executed)
        return reply, "\n\n".join(reasonings) or None, executed

    def _parse_response(self, raw: str) -> tuple[str, list[ChatAction]]:
        data = self._extract_json(raw)
        if isinstance(data, dict):
            reply = data.get("reply", raw)
            actions_raw = data.get("actions", [])
            actions = [
                ChatAction(
                    type=a.get("type", "unknown"),
                    params=a.get("params", {}),
                    status="pending",
                )
                for a in actions_raw
                if isinstance(a, dict)
            ]
            return reply, actions
        return raw, []

    @staticmethod
    def _extract_json(raw: str):
        """Pull a JSON object out of an LLM response.

        Models routinely wrap the payload in a markdown ```json fence and/or
        prepend natural-language text ("Добавлю расход..."). Naive json.loads
        on the whole string then fails and silently drops every action — so
        try the raw string first, then fenced blocks, then the outermost
        brace slice. Returns None when nothing parseable is found."""
        if not isinstance(raw, str):
            return None
        text = raw.strip()
        # 1. Whole response is already pure JSON
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass
        # 2. Fenced block: ```json ... ``` (or ``` ... ```)
        fence_re = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
        for match in fence_re.finditer(text):
            try:
                return json.loads(match.group(1))
            except (json.JSONDecodeError, TypeError):
                continue
        # 3. Outermost braces around whatever JSON the model embedded
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    async def _execute_action(self, action: ChatAction) -> ChatAction:
        try:
            if action.type == "create_transaction":
                return await self._create_transaction(action)
            elif action.type == "update_transaction":
                return await self._update_transaction(action)
            elif action.type == "delete_transaction":
                return await self._delete_transaction(action)
            elif action.type == "list_transactions":
                return await self._list_transactions(action)
            elif action.type == "create_category":
                return await self._create_category(action)
            elif action.type == "create_account":
                return await self._create_account(action)
            else:
                action.status = "failed"
                action.error = f"Unknown action type: {action.type}"
        except Exception as e:
            logger.exception("Failed to execute chat action")
            action.status = "failed"
            action.error = str(e)
        return action

    def _actions_summary(self, actions: list[ChatAction]) -> str:
        """Plain-text wrap-up used when the model never got around to a
        final reply (tool round budget spent / empty completion)."""
        if not actions:
            return "Done."
        done = [a for a in actions if a.status == "executed"]
        failed = [a for a in actions if a.status == "failed"]
        lines = [f"Done: {a.result or a.type}" for a in done]
        lines += [f"Failed: {a.type} — {a.error}" for a in failed]
        return "\n".join(lines)

    async def _create_transaction(self, action: ChatAction) -> ChatAction:
        from app.models.enums import TransactionType as TT
        params = action.params
        # Required tool args checked up front: a model that skips one used
        # to blow up on params["…"] and report a bare KeyError back to the
        # user, which says nothing about what it got wrong.
        missing = [k for k in ("account_id", "amount") if params.get(k) is None]
        if missing:
            action.status = "failed"
            action.error = f"create_transaction is missing required field(s): {', '.join(missing)}"
            return action
        tx = Transaction(
            account_id=params["account_id"],
            type=TT(params.get("type", "expense")),
            amount=params["amount"],
            description=params.get("description", ""),
            date=date.fromisoformat(params["date"]) if "date" in params else date.today(),
            category_id=params.get("category_id"),
        )
        self.session.add(tx)
        await self.session.flush()
        action.status = "executed"
        action.result = f"Created transaction #{tx.id}: {tx.amount} {tx.type.value}"
        return action

    async def _update_transaction(self, action: ChatAction) -> ChatAction:
        from app.models.enums import TransactionType as TT
        params = action.params
        tx = await self.session.get(Transaction, params.get("transaction_id"))
        if tx is None:
            action.status = "failed"
            action.error = f"Transaction {params.get('transaction_id')} not found"
            return action

        # Only fields the model actually sent — a partial update must not
        # blank out description/category just because they were absent.
        if "account_id" in params:
            tx.account_id = params["account_id"]
        if "type" in params:
            tx.type = TT(params["type"])
        if "amount" in params:
            tx.amount = params["amount"]
        if "description" in params:
            tx.description = params["description"]
        if "date" in params and params["date"]:
            tx.date = date.fromisoformat(params["date"])
        if "category_id" in params:
            tx.category_id = params["category_id"]
        await self.session.flush()
        action.status = "executed"
        action.result = f"Updated transaction #{tx.id}: {tx.amount} {tx.type.value}"
        return action

    async def _list_transactions(self, action: ChatAction) -> ChatAction:
        """Read-only period query — feeds the model numbers to analyze,
        and its result travels back via the tool-result message."""
        params = action.params
        stmt = select(Transaction).order_by(Transaction.date.desc())
        if params.get("date_from"):
            stmt = stmt.where(Transaction.date >= date.fromisoformat(params["date_from"]))
        if params.get("date_to"):
            stmt = stmt.where(Transaction.date <= date.fromisoformat(params["date_to"]))
        if params.get("account_id"):
            stmt = stmt.where(Transaction.account_id == params["account_id"])
        if params.get("category_id"):
            stmt = stmt.where(Transaction.category_id == params["category_id"])
        stmt = stmt.limit(int(params.get("limit") or 50))

        rows = (await self.session.execute(stmt)).scalars().all()
        action.status = "executed"
        action.result = json.dumps(
            [
                {
                    "id": t.id,
                    "date": t.date.isoformat(),
                    "type": t.type.value,
                    "amount": str(t.amount),
                    "description": t.description,
                    "category_id": t.category_id,
                    "account_id": t.account_id,
                }
                for t in rows
            ],
            ensure_ascii=False,
        )
        return action

    async def _create_category(self, action: ChatAction) -> ChatAction:
        from app.models.enums import CategoryKind as CK

        params = action.params
        cat = Category(name=params["name"], kind=CK(params["kind"]))
        self.session.add(cat)
        await self.session.flush()
        action.status = "executed"
        action.result = f"Created category #{cat.id}: {cat.name}"
        return action

    async def _create_account(self, action: ChatAction) -> ChatAction:
        from app.models.enums import AccountType as AT

        params = action.params
        account = Account(
            name=params["name"],
            type=AT(params.get("type", "other")),
            currency=params.get("currency") or get_settings().default_currency,
            color="#2a78d6",
        )
        self.session.add(account)
        await self.session.flush()
        action.status = "executed"
        action.result = f"Created account #{account.id}: {account.name}"
        return action

    async def _delete_transaction(self, action: ChatAction) -> ChatAction:
        tx_id = action.params.get("transaction_id")
        if tx_id is None:
            action.status = "failed"
            action.error = "transaction_id is required"
            return action
        tx = await self.session.get(Transaction, tx_id)
        if tx is None:
            action.status = "failed"
            action.error = f"Transaction {tx_id} not found"
            return action
        await self.session.delete(tx)
        await self.session.flush()
        action.status = "executed"
        action.result = f"Deleted transaction #{tx_id}"
        return action
