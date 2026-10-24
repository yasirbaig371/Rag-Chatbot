from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.chat import MessageRole


class ChatSessionCreate(BaseModel):
    document_id: Optional[int] = Field(default=None, gt=0)


class ChatMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message cannot be blank.")
        return cleaned


class ChatMessageRead(BaseModel):
    id: int
    role: MessageRole
    content: str
    sources: Optional[List[dict[str, Any]]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatSessionSummary(BaseModel):
    id: int
    document_id: Optional[int] = None
    document_title: Optional[str] = None
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ChatSessionDetail(BaseModel):
    id: int
    document_id: Optional[int] = None
    document_title: Optional[str] = None
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[ChatMessageRead]


class ChatMessageResponse(BaseModel):
    user_message: ChatMessageRead
    assistant_message: ChatMessageRead
