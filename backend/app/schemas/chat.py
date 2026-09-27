"""Pydantic schemas for the chat/AI agent feature."""
from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    session_id: int | None = None
    attachment_ids: list[int] = []


class ChatAction(BaseModel):
    type: str
    params: dict = {}
    status: str = "pending"  # pending | executed | failed
    result: str | None = None
    error: str | None = None


class ChatAttachmentRead(BaseModel):
    id: int
    message_id: int
    filename: str
    content_type: str
    size: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageRead(BaseModel):
    id: int
    role: str
    content: str
    # Model's chain-of-thought when the backend produced one — the
    # frontend shows it only when the user ticks "show reasoning".
    reasoning: str | None = None
    actions: list[ChatAction] = []
    attachments: list[ChatAttachmentRead] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionRead(BaseModel):
    id: int
    title: str | None
    created_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    session_id: int
    message: ChatMessageRead
    reply: str
