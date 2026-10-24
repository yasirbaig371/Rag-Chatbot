from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_active_user
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import (
    get_password_hash,
    verify_password,
    hash_token,
    generate_secure_token,
    create_access_token,
)
from app.models.auth_session import AuthSession
from app.models.user import User, UserRole
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
)
from app.schemas.user import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def set_refresh_cookie(response: Response, raw_token: str) -> None:
    """Sets the HttpOnly refresh token cookie with configured security flags."""
    max_age_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=max_age_seconds,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/api/auth",
    )


def clear_refresh_cookie(response: Response) -> None:
    """Clears the HttpOnly refresh token cookie matching the path and domain flags."""
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path="/api/auth",
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )


def validate_request_origin(request: Request) -> None:
    """Validates the Origin header for sensitive cookie-authenticated operations in production."""
    origin = request.headers.get("origin")
    if settings.ENVIRONMENT != "development" and origin:
        allowed = settings.cors_origins_list
        if origin not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Untrusted cross-origin request rejected",
            )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(
    data: UserRegisterRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Any:
    """Registers users directly and holds administrator registrations for approval."""
    normalized_email = data.email.strip().lower()

    # Case-insensitive duplicate check
    existing_user = db.scalar(
        select(User).where(func.lower(User.email) == normalized_email)
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists",
        )

    user = User(
        full_name=data.full_name,
        email=normalized_email,
        password_hash=get_password_hash(data.password),
        role=data.role,
        is_active=data.role != UserRole.ADMIN,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(
    request: Request,
    response: Response,
    data: UserLoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Any:
    """Authenticates user with rate-limiting (5/min), issues HS256 JWT access token and rotates refresh cookie."""
    normalized_email = data.email.strip().lower()
    user = db.scalar(
        select(User).where(func.lower(User.email) == normalized_email)
    )

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    # 1. Generate access token
    access_token = create_access_token(
        subject=user.id,
        role=user.role.value,
    )

    # 2. Generate and persist refresh token session in auth_sessions table
    raw_refresh_token = generate_secure_token(64)
    token_h = hash_token(raw_refresh_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    session_record = AuthSession(
        user_id=user.id,
        token_hash=token_h,
        expires_at=expires_at,
    )
    db.add(session_record)
    db.commit()

    # 3. Set HttpOnly cookie
    set_refresh_cookie(response, raw_refresh_token)

    return TokenResponse(access_token=access_token, token_type="bearer")


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> Any:
    """Rotates refresh session using HttpOnly cookie and returns a new access token."""
    validate_request_origin(request)

    raw_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token cookie missing",
        )

    token_h = hash_token(raw_token)
    session_record = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == token_h)
    )

    if not session_record:
        clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh session",
        )

    # Detect refresh token reuse: if already revoked, potential token theft!
    if session_record.revoked_at is not None:
        # Revoke ALL active sessions for this user for security
        now = datetime.now(timezone.utc)
        db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == session_record.user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        db.commit()
        clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected. All sessions revoked for security.",
        )

    now = datetime.now(timezone.utc)
    if session_record.expires_at < now:
        session_record.revoked_at = now
        db.commit()
        clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh session has expired",
        )

    # Check user active status
    user = db.get(User, session_record.user_id)
    if not user or not user.is_active:
        session_record.revoked_at = now
        db.commit()
        clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated or no longer exists",
        )

    # Perform safe token rotation
    session_record.revoked_at = now

    new_raw_token = generate_secure_token(64)
    new_token_h = hash_token(new_raw_token)
    new_expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    new_session = AuthSession(
        user_id=user.id,
        token_hash=new_token_h,
        expires_at=new_expires,
    )
    db.add(new_session)
    db.flush()

    session_record.replaced_by_session_id = new_session.id
    db.commit()

    # Set new rotated refresh cookie
    set_refresh_cookie(response, new_raw_token)

    # Issue new access token
    new_access_token = create_access_token(
        subject=user.id,
        role=user.role.value,
    )
    return TokenResponse(access_token=new_access_token, token_type="bearer")


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> Any:
    """Revokes refresh session and clears the HttpOnly cookie."""
    validate_request_origin(request)

    raw_token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if raw_token:
        token_h = hash_token(raw_token)
        session_record = db.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_h)
        )
        if session_record and session_record.revoked_at is None:
            session_record.revoked_at = datetime.now(timezone.utc)
            db.commit()

    clear_refresh_cookie(response)
    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserRead)
def read_current_user_profile(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Any:
    """Returns the profile of the currently authenticated active user."""
    return current_user
