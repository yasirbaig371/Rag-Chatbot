from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.models.user import UserRole
from app.schemas.auth import UserRegisterRequest
from app.schemas.user import UserRead


class AdminUserCreate(UserRegisterRequest):
    role: UserRole = UserRole.USER


class AdminUserPage(BaseModel):
    items: List[UserRead]
    total: int
    limit: int
    offset: int


class AdminStatistics(BaseModel):
    users: int
    active_users: int
    documents: int
    ready_documents: int
    chat_sessions: int
    chat_messages: int


class AdminSessionRead(BaseModel):
    id: int
    user_id: int
    user_email: str
    document_id: Optional[int] = None
    document_title: Optional[str] = None
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime
