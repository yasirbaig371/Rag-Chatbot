import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth_session import AuthSession
from app.models.user import User, UserRole


def test_get_users_me(client: TestClient):
    """Test retrieving current user profile via /users/me."""
    client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"full_name": "Hannah", "email": "hannah@example.com", "password": "Password123!"},
    )
    login_res = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "hannah@example.com", "password": "Password123!"},
    )
    access_token = login_res.json()["access_token"]

    res = client.get(
        f"{settings.API_V1_STR}/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "hannah@example.com"
    assert data["full_name"] == "Hannah"
    assert data["role"] == "user"
    assert "password_hash" not in data


def test_update_users_me_and_role_escalation_prevention(client: TestClient):
    """Test updating user profile and ensure role escalation is strictly prevented."""
    client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"full_name": "Ian Original", "email": "ian@example.com", "password": "Password123!"},
    )
    login_res = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "ian@example.com", "password": "Password123!"},
    )
    token = login_res.json()["access_token"]

    # Attempt to escalate role to admin via PATCH /users/me
    patch_res = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"full_name": "Ian Updated", "role": "admin"},
    )
    assert patch_res.status_code == 200
    updated_data = patch_res.json()
    assert updated_data["full_name"] == "Ian Updated"
    # Role MUST remain user!
    assert updated_data["role"] == "user"


def test_change_password_flow(client: TestClient, db_session: Session):
    """Test changing password, checking old vs new password, and verifying session revocation."""
    client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"full_name": "Julia", "email": "julia@example.com", "password": "OldPassword123!"},
    )
    login_res = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "julia@example.com", "password": "OldPassword123!"},
    )
    token = login_res.json()["access_token"]

    # 1. Wrong current password
    bad_res = client.post(
        f"{settings.API_V1_STR}/users/me/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "WrongPassword!", "new_password": "NewPassword123!"},
    )
    assert bad_res.status_code == 400

    # 2. Short new password
    short_res = client.post(
        f"{settings.API_V1_STR}/users/me/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "OldPassword123!", "new_password": "short"},
    )
    assert short_res.status_code == 422

    # 3. Successful password change
    good_res = client.post(
        f"{settings.API_V1_STR}/users/me/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "OldPassword123!", "new_password": "NewPassword123!"},
    )
    assert good_res.status_code == 200

    # Verify old password no longer works
    fail_login = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "julia@example.com", "password": "OldPassword123!"},
    )
    assert fail_login.status_code == 401

    # Verify new password logs in successfully
    success_login = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "julia@example.com", "password": "NewPassword123!"},
    )
    assert success_login.status_code == 200

    # Verify all prior auth sessions are revoked in auth_sessions table
    user = db_session.scalar(select(User).where(User.email == "julia@example.com"))
    sessions = db_session.scalars(
        select(AuthSession).where(AuthSession.user_id == user.id)
    ).all()
    # Initial login session must be revoked
    revoked_count = sum(1 for s in sessions if s.revoked_at is not None)
    assert revoked_count >= 1
