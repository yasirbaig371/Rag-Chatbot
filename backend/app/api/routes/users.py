from datetime import datetime, timezone
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_active_user
from app.api.routes.auth import clear_refresh_cookie
from app.core.security import get_password_hash, verify_password
from app.models.auth_session import AuthSession
from app.models.user import User
from app.schemas.auth import PasswordChangeRequest
from app.schemas.user import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
def get_user_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Any:
    """Retrieves the profile of the currently authenticated active user."""
    return current_user


@router.patch("/me", response_model=UserRead)
def update_user_me(
    data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Any:
    """Updates editable profile information for the current user (role is protected against escalation)."""
    if data.full_name is not None:
        cleaned_name = data.full_name.strip()
        if not cleaned_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Full name cannot be blank",
            )
        current_user.full_name = cleaned_name

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/me/change-password")
def change_password(
    data: PasswordChangeRequest,
    response: Response,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Any:
    """Changes password for the current user and revokes all active refresh sessions for account security."""
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password",
        )

    if len(data.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New password must be at least 8 characters long",
        )

    # 1. Update password hash
    current_user.password_hash = get_password_hash(data.new_password)
    db.add(current_user)

    # 2. Security requirement: Revoke all active refresh sessions for this user
    now = datetime.now(timezone.utc)
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == current_user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.commit()

    # 3. Clear current refresh cookie
    clear_refresh_cookie(response)

    return {"message": "Password updated successfully. Please log in again with your new password."}
