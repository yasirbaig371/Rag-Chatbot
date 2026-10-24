import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models.auth_session import AuthSession
from app.models.user import User, UserRole


def test_register_success(client: TestClient):
    """Test successful user registration with sanitized input."""
    payload = {
        "full_name": "  Alice Smith  ",
        "email": "Alice@Example.COM",
        "password": "Password123!",
    }
    response = client.post(f"{settings.API_V1_STR}/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["full_name"] == "Alice Smith"
    assert data["email"] == "alice@example.com"
    assert data["role"] == "user"
    assert data["is_active"] is True
    assert "password_hash" not in data


def test_admin_registration_requires_admin_approval(
    client: TestClient,
    db_session: Session,
):
    response = client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={
            "full_name": "Pending Admin",
            "email": "pending-admin@example.com",
            "password": "Password123!",
            "role": "admin",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "admin"
    assert response.json()["is_active"] is False
    account = db_session.get(User, response.json()["id"])
    assert account is not None
    assert account.is_active is False

    login = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "pending-admin@example.com", "password": "Password123!"},
    )
    assert login.status_code == 403

    existing_admin = User(
        full_name="Existing Admin",
        email="existing-admin@example.com",
        password_hash=get_password_hash("Password123!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(existing_admin)
    db_session.commit()
    db_session.refresh(existing_admin)
    token = create_access_token(subject=existing_admin.id, role=existing_admin.role.value)

    approval = client.patch(
        f"{settings.API_V1_STR}/admin/users/{account.id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": True},
    )
    assert approval.status_code == 200
    assert approval.json()["is_active"] is True

    approved_login = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "pending-admin@example.com", "password": "Password123!"},
    )
    assert approved_login.status_code == 200


def test_register_duplicate_email(client: TestClient):
    """Test case-insensitive duplicate email rejection."""
    payload1 = {
        "full_name": "Bob First",
        "email": "bob@example.com",
        "password": "Password123!",
    }
    client.post(f"{settings.API_V1_STR}/auth/register", json=payload1)

    payload2 = {
        "full_name": "Bob Second",
        "email": "BOB@EXAMPLE.COM",
        "password": "DifferentPassword123!",
    }
    response = client.post(f"{settings.API_V1_STR}/auth/register", json=payload2)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


def test_register_invalid_inputs(client: TestClient):
    """Test input validations: short password, invalid email, blank name."""
    # Short password
    r1 = client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"full_name": "Test", "email": "test@test.com", "password": "short"},
    )
    assert r1.status_code == 422

    # Invalid email
    r2 = client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"full_name": "Test", "email": "not-an-email", "password": "Password123!"},
    )
    assert r2.status_code == 422

    # Blank name
    r3 = client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"full_name": "   ", "email": "test@test.com", "password": "Password123!"},
    )
    assert r3.status_code == 422


def test_login_success_and_cookie(client: TestClient):
    """Test successful login returns access token and sets HttpOnly refresh cookie."""
    # Register user
    client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"full_name": "Charlie", "email": "charlie@example.com", "password": "Password123!"},
    )

    # Login
    response = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "CHARLIE@EXAMPLE.COM", "password": "Password123!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert settings.REFRESH_COOKIE_NAME in response.cookies


def test_login_wrong_password(client: TestClient):
    """Test login with incorrect password."""
    client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"full_name": "Dave", "email": "dave@example.com", "password": "Password123!"},
    )
    response = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "dave@example.com", "password": "WrongPassword!"},
    )
    assert response.status_code == 401


def test_login_deactivated_user(client: TestClient, db_session: Session):
    """Test deactivated user cannot log in."""
    user = User(
        full_name="Deactivated",
        email="inactive@example.com",
        password_hash=get_password_hash("Password123!"),
        role=UserRole.USER,
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()

    response = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "inactive@example.com", "password": "Password123!"},
    )
    assert response.status_code == 403
    assert "deactivated" in response.json()["detail"].lower()


def test_refresh_token_rotation(client: TestClient):
    """Test refresh token rotation issues new access token and new cookie."""
    client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"full_name": "Eve", "email": "eve@example.com", "password": "Password123!"},
    )
    login_res = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "eve@example.com", "password": "Password123!"},
    )
    first_cookie = login_res.cookies[settings.REFRESH_COOKIE_NAME]
    first_access_token = login_res.json()["access_token"]

    # Call refresh
    refresh_res = client.post(f"{settings.API_V1_STR}/auth/refresh")
    assert refresh_res.status_code == 200
    second_cookie = refresh_res.cookies[settings.REFRESH_COOKIE_NAME]
    second_access_token = refresh_res.json()["access_token"]

    assert second_cookie != first_cookie
    assert second_access_token != first_access_token


def test_refresh_token_reuse_detection(client: TestClient, db_session: Session):
    """Test reusing an old rotated refresh token triggers security revocation of all sessions."""
    client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"full_name": "Frank", "email": "frank@example.com", "password": "Password123!"},
    )
    login_res = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "frank@example.com", "password": "Password123!"},
    )
    stale_token = login_res.cookies[settings.REFRESH_COOKIE_NAME]

    # Normal rotation: rotates stale_token to new_token
    refresh_res = client.post(f"{settings.API_V1_STR}/auth/refresh")
    assert refresh_res.status_code == 200

    # Attacker tries to use the stale rotated token!
    client.cookies.set(settings.REFRESH_COOKIE_NAME, stale_token)
    reuse_res = client.post(f"{settings.API_V1_STR}/auth/refresh")
    assert reuse_res.status_code == 401
    assert "reuse detected" in reuse_res.json()["detail"].lower()


def test_logout_and_auth_me(client: TestClient):
    """Test logout clears refresh cookie and revokes session, and GET /me returns current profile."""
    client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"full_name": "Grace", "email": "grace@example.com", "password": "Password123!"},
    )
    login_res = client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={"email": "grace@example.com", "password": "Password123!"},
    )
    access_token = login_res.json()["access_token"]

    # GET /me with Bearer token
    me_res = client.get(
        f"{settings.API_V1_STR}/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "grace@example.com"

    # Logout
    logout_res = client.post(f"{settings.API_V1_STR}/auth/logout")
    assert logout_res.status_code == 200

    # Trying to refresh after logout should fail
    refresh_res = client.post(f"{settings.API_V1_STR}/auth/refresh")
    assert refresh_res.status_code == 401


def test_login_rate_limiting(db_session: Session):
    """Test that login enforces the 5 requests per minute rate limit."""
    from app.core.rate_limit import limiter
    limiter.enabled = True
    try:
        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app) as tc:
            tc.post(
                f"{settings.API_V1_STR}/auth/register",
                json={"full_name": "Rate Limit User", "email": "ratelimit@example.com", "password": "Password123!"},
            )
            # Make 5 allowed attempts
            for _ in range(5):
                res = tc.post(
                    f"{settings.API_V1_STR}/auth/login",
                    json={"email": "ratelimit@example.com", "password": "Password123!"},
                )
                assert res.status_code == 200

            # 6th attempt within the same minute should be rate limited (HTTP 429)
            blocked_res = tc.post(
                f"{settings.API_V1_STR}/auth/login",
                json={"email": "ratelimit@example.com", "password": "Password123!"},
            )
            assert blocked_res.status_code == 429
            assert "too many requests" in blocked_res.json()["detail"].lower()
    finally:
        limiter.enabled = False
        app.dependency_overrides.clear()
