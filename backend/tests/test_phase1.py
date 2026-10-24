import psycopg
import pytest
from app.core.config import settings
from app.core.security import (
    get_password_hash,
    verify_password,
    hash_token,
    create_access_token,
    decode_access_token,
)


def test_test_database_connection():
    """Verify that rag_test_db is accessible using rag_user."""
    conn = psycopg.connect(settings.TEST_DATABASE_URL.replace("+psycopg", ""))
    cur = conn.cursor()
    cur.execute("SELECT current_database();")
    result = cur.fetchone()
    conn.close()
    assert result is not None
    assert result[0] == "rag_test_db"


def test_argon2_password_hashing():
    """Verify Argon2id password hashing and verification."""
    password = "SuperSecretPassword123!"
    hashed = get_password_hash(password)
    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_token_hash_sha256():
    """Verify SHA-256 token hashing for auth_sessions."""
    token = "some-random-refresh-token"
    token_h = hash_token(token)
    assert len(token_h) == 64
    assert token_h == hash_token(token)


def test_jwt_access_token_creation_and_decode():
    """Verify HS256 JWT access token generation and validation."""
    token = create_access_token(subject=1, role="user")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "1"
    assert payload["role"] == "user"
    assert payload["type"] == "access"
