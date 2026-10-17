"""Chat / AI agent endpoints."""
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.llm.errors import LLMProviderError
from app.api.llm.registry import get_provider
from app.core.config import get_settings
from app.models.chat import ChatAttachment, ChatMessage, ChatSession
from app.schemas.chat import (
    ChatAttachmentRead,
    ChatMessageRead,
    ChatRequest,
    ChatResponse,
    ChatSessionRead,
)
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])

# Max attachment size: 10 MB
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024

# Allowed MIME types for attachments
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "text/csv",
    "text/plain",
    "application/json",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}


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
        return await svc.process_message(
            payload.message, payload.session_id, payload.attachment_ids or None
        )
    except LLMProviderError as e:
        # The LLM endpoint's own answer (bad key, rate limit, outage) — a
        # gateway-level failure, not an Aurum bug: 502 with the readable
        # detail instead of an unhandled 500 the UI can only call
        # "internal server error".
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/attachments/upload")
async def upload_attachment(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    """Upload a file attachment to be included in a chat message."""
    from app.core.config import get_settings
    import uuid
    from pathlib import Path
    
    settings = get_settings()
    upload_dir = Path(settings.upload_dir) / "chat_attachments"
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    file_ext = Path(file.filename).suffix
    unique_name = f"{uuid.uuid4().hex}{file_ext}"
    file_path = upload_dir / unique_name
    
    # Save file
    content = await file.read()
    file_path.write_bytes(content)
    
    # Create attachment record (message_id NULL — linked when the message is sent)
    attachment = ChatAttachment(
        message_id=None,  # Will be linked when message is sent
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size=len(content),
        file_path=str(file_path),
    )
    session.add(attachment)
    await session.commit()
    await session.refresh(attachment)
    
    return {
        "id": attachment.id,
        "filename": attachment.filename,
        "content_type": attachment.content_type,
        "size": attachment.size,
    }


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Download an attachment file."""
    attachment = await session.get(ChatAttachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    from pathlib import Path
    file_path = Path(attachment.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    return FileResponse(
        path=file_path,
        filename=attachment.filename,
        media_type=attachment.content_type,
    )


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
            attachments=[
                ChatAttachmentRead.model_validate(att) for att in m.attachments
            ],
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


def _get_upload_dir() -> Path:
    """Get or create the directory for chat attachment uploads."""
    settings = get_settings()
    upload_dir = Path(settings.upload_dir) / "chat_attachments"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


@router.post("/attachments", response_model=ChatAttachmentRead)
async def upload_attachment(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> ChatAttachmentRead:
    """Upload a file attachment for a chat message.
    
    The file is saved to disk and a ChatAttachment row is created.
    The attachment is not yet linked to a message — that happens when
    the message is sent with attachment_ids.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{file.content_type}' not allowed. Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}",
        )
    
    # Read file content to check size
    content = await file.read()
    if len(content) > MAX_ATTACHMENT_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large ({len(content)} bytes). Max: {MAX_ATTACHMENT_SIZE} bytes",
        )
    
    # Generate unique filename
    file_ext = Path(file.filename).suffix
    unique_name = f"{uuid.uuid4().hex}{file_ext}"
    
    # Save to disk
    upload_dir = _get_upload_dir()
    file_path = upload_dir / unique_name
    file_path.write_bytes(content)
    
    # Create DB row (message_id is null — will be linked when message is sent)
    attachment = ChatAttachment(
        message_id=None,  # Will be updated when message is sent
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
        size=len(content),
        file_path=str(file_path),
    )
    session.add(attachment)
    await session.commit()
    await session.refresh(attachment)
    
    return ChatAttachmentRead.model_validate(attachment)


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: int,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    """Download a chat attachment file."""
    attachment = await session.get(ChatAttachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    file_path = Path(attachment.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    return FileResponse(
        path=file_path,
        filename=attachment.filename,
        media_type=attachment.content_type,
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete a chat attachment (and its file from disk)."""
    attachment = await session.get(ChatAttachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    # Delete file from disk
    file_path = Path(attachment.file_path)
    if file_path.exists():
        file_path.unlink()
    
    # Delete DB row
    await session.delete(attachment)
    await session.commit()
