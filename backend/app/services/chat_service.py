"""Chat service — orchestrates context building, LLM calls, and action execution."""
import json
import logging
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.llm import get_provider
from app.core.config import Settings
from app.models.account import Account
from app.models.category import Category
from app.models.chat import ChatMessage, ChatSession
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.schemas.chat import ChatAction, ChatMessageRead, ChatResponse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Aurum's financial assistant. You can read the user's
financial data (accounts, transactions, budgets, categories) and help them manage
their personal finances.

When the user asks you to create, update, or delete financial records, respond
with a JSON object containing:
- "reply": a natural language response to the user
- "actions": a list of action objects, each with:
  - "type": the action name (e.g. "create_transaction", "delete_transaction")
  - "params": a dict of parameters for the action
  - "status": "pending"

Supported action types:
- create_transaction: {account_id, type, amount, description, date, category_id?}
- delete_transaction: {transaction_id}
- create_category: {name, kind}
- create_account: {name, type, currency}

Always explain what you're going to do before performing actions.
If no actions are needed, return just {"reply": "...", "actions": []}.

Respond in the same language the user writes in."""


class ChatService:
    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.provider = get_provider(settings)
        self.settings = settings

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

        raw_response = await self.provider.chat(messages)

        # 4. Parse response
        reply_text, actions = self._parse_response(raw_response)

        # 5. Execute actions
        executed_actions = []
        for action in actions:
            result = await self._execute_action(action)
            executed_actions.append(result)

        # 6. Save assistant message
        assistant_msg = ChatMessage(
            session_id=chat_session.id,
            role="assistant",
            content=reply_text,
            actions_json=json.dumps([a.model_dump() for a in executed_actions]),
        )
        self.session.add(assistant_msg)
        await self.session.commit()

        return ChatResponse(
            session_id=chat_session.id,
            message=ChatMessageRead(
                id=assistant_msg.id,
                role="assistant",
                content=reply_text,
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

    def _parse_response(self, raw: str) -> tuple[str, list[ChatAction]]:
        try:
            data = json.loads(raw)
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
        except (json.JSONDecodeError, TypeError):
            pass
        return raw, []

    async def _execute_action(self, action: ChatAction) -> ChatAction:
        try:
            if action.type == "create_transaction":
                return await self._create_transaction(action)
            elif action.type == "delete_transaction":
                return await self._delete_transaction(action)
            else:
                action.status = "failed"
                action.error = f"Unknown action type: {action.type}"
        except Exception as e:
            logger.exception("Failed to execute chat action")
            action.status = "failed"
            action.error = str(e)
        return action

    async def _create_transaction(self, action: ChatAction) -> ChatAction:
        from app.models.enums import TransactionType as TT
        params = action.params
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
