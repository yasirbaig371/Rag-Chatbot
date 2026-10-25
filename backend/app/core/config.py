import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import computed_field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application Settings
    PROJECT_NAME: str = "Multi-Role RAG Chatbot"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api"
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000

    # PostgreSQL Database URLs (psycopg 3)
    DATABASE_URL: str = "postgresql+psycopg://rag_user:rag_password@localhost:5432/rag_db"
    TEST_DATABASE_URL: str = "postgresql+psycopg://rag_user:rag_password@localhost:5432/rag_test_db"

    # JWT & Authentication Security
    JWT_SECRET: str = "replace-with-a-secure-random-secret-key-at-least-32-chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"

    # CORS Origins (comma-separated string or list)
    CORS_ORIGINS: str = "http://localhost:5173"

    @computed_field
    @property
    def cors_origins_list(self) -> List[str]:
        if not self.CORS_ORIGINS:
            return ["http://localhost:5173"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # OpenRouter LLM Configuration
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"

    # Storage & Vector Database Paths
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # RAG & Embedding Settings
    GEMINI_API_KEY: str = ""
    EMBEDDING_MODEL_NAME: str = "models/text-embedding-004"
    RAG_TOP_K: int = 4
    RAG_DISTANCE_THRESHOLD: float = 1.2


settings = Settings()
