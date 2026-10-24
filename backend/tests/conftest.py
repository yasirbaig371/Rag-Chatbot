import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.base import Base
from app.main import app

# Safety assertion: tests MUST run only on rag_test_db
assert "rag_test_db" in settings.TEST_DATABASE_URL, (
    f"FATAL SAFETY CHECK: TEST_DATABASE_URL ({settings.TEST_DATABASE_URL}) "
    "does not point to rag_test_db! Aborting to protect development data."
)

test_engine = create_engine(
    settings.TEST_DATABASE_URL,
    pool_pre_ping=True,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Ensures test database tables exist before running test suite."""
    Base.metadata.create_all(bind=test_engine)
    yield
    # No drop_all needed; tables remain for inspection if needed


@pytest.fixture(scope="function")
def db_session() -> Session:
    """Provides a fresh transactional session and truncates test tables after each test."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        # Clean up data between tests
        with test_engine.connect() as conn:
            conn.execute(
                text(
                    "TRUNCATE TABLE auth_sessions, chat_messages, chat_sessions, documents, users RESTART IDENTITY CASCADE;"
                )
            )
            conn.commit()


@pytest.fixture(scope="function")
def client(db_session: Session) -> TestClient:
    """FastAPI TestClient with get_db overridden to use the isolated test database."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    limiter.enabled = False
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    limiter.enabled = True
