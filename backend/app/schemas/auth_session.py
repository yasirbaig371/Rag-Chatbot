from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class AuthSessionRead(BaseModel):
    id: int
    user_id: int
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    created_at: datetime
    last_used_at: datetime

    model_config = ConfigDict(from_attributes=True)
