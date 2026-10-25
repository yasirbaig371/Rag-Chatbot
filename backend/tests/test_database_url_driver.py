import pytest

from app.core.config import Settings


@pytest.mark.parametrize("field", ["DATABASE_URL", "TEST_DATABASE_URL"])
@pytest.mark.parametrize(
    ("database_url", "expected_url"),
    [
        (
            "postgres://dbuser:dbpass@localhost:5432/rag",
            "postgresql+psycopg://dbuser:dbpass@localhost:5432/rag",
        ),
        (
            "postgresql://dbuser:dbpass@localhost:5432/rag",
            "postgresql+psycopg://dbuser:dbpass@localhost:5432/rag",
        ),
        (
            "postgresql+psycopg://dbuser:dbpass@localhost:5432/rag",
            "postgresql+psycopg://dbuser:dbpass@localhost:5432/rag",
        ),
    ],
)
def test_postgresql_urls_use_psycopg3(
    field: str, database_url: str, expected_url: str
) -> None:
    settings = Settings(**{field: database_url})

    assert getattr(settings, field) == expected_url
