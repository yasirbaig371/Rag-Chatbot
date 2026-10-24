from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus


class DocumentBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    is_public: bool = True


class DocumentRead(DocumentBase):
    id: int
    filename: str
    uploader_id: int
    chroma_collection: str
    chunk_count: int
    page_count: Optional[int] = None
    file_hash: Optional[str] = None
    status: DocumentStatus
    processing_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentVisibilityUpdate(BaseModel):
    is_public: bool = Field(..., description="Set whether the document is publicly accessible to all users")
