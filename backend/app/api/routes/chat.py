"""Chat / AI agent endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.llm.registry import get_provider
from app.models.chat import ChatMessage, ChatSession
from app.schemas.chat import (
    ChatMessageRead,
    ChatRequest,
    ChatResponse,
    ChatSessionRead,
)
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def send_message(
    payload: ChatRequest, session: AsyncSession = Depends(get_session)
) -> ChatResponse:
    # Backend mode/provider/model come from the llm_* tables (Settings →
    # AI), not env — resolved fresh per request so a switch in the UI takes
    # effect on the next message without a restart.
    from app.services.llm_service import get_llm_config

    config = await get_llm_config(session)
    try:
        provider = get_provider(config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    svc = ChatService(session, provider, config)
    try:
        return await svc.process_message(payload.message, payload.session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/sessions", response_model=list[ChatSessionRead])
async def list_sessions(
    session: AsyncSession = Depends(get_session),
) -> list[ChatSessionRead]:
    stmt = (
        select(
            ChatSession,
            func.count(ChatMessage.id).label("message_count"),
        )
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        ChatSessionRead(
            id=row.ChatSession.id,
            title=row.ChatSession.title,
            created_at=row.ChatSession.created_at,
            message_count=row.message_count,
        )
        for row in rows
    ]


@router.get(
    "/sessions/{session_id}/messages", response_model=list[ChatMessageRead]
)
async def list_messages(
    session_id: int, session: AsyncSession = Depends(get_session)
) -> list[ChatMessageRead]:
    chat_session = await session.get(ChatSession, session_id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = (await session.execute(stmt)).scalars().all()
    return [
        ChatMessageRead(
            id=m.id,
            role=m.role,
            content=m.content,
            reasoning=m.reasoning,
            actions=_parse_actions(m.actions_json),
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    chat_session = await session.get(ChatSession, session_id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    await session.delete(chat_session)
    await session.commit()


def _parse_actions(actions_json: str | None) -> list:
    if not actions_json:
        return []
    try:
        import json
        return json.loads(actions_json)
    except (json.JSONDecodeError, TypeError):
        return []
