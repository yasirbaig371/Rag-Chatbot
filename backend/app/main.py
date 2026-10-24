from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from fastapi import FastAPI, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api.api import api_router
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.session import SessionLocal
from app.services.chroma_service import get_embedding_model


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Load the local embedding model before accepting chat requests."""
    await run_in_threadpool(get_embedding_model)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Multi-Role RAG Chatbot API with Role-Based Access Control, Document Ingestion, and OpenRouter LLM",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Attach rate limiter state and middleware
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Returns a safe, user-friendly 429 message when rate limits are exceeded."""
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Too many requests. Please slow down and try again later."},
    )


# Configure CORS with explicit allowed frontend origins and credentials support
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["system"])
def root_status() -> dict[str, str]:
    """Basic root service ping."""
    return {
        "project": settings.PROJECT_NAME,
        "status": "online",
        "docs": "/docs",
    }


@app.get("/health/live", tags=["health"])
def health_liveness() -> dict[str, str]:
    """Liveness probe: verifies that the FastAPI process is running."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def health_readiness() -> JSONResponse:
    """Readiness probe: safely verifies PostgreSQL database connectivity without leaking credentials."""
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready", "database": "connected"},
        )
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable", "database": "unreachable"},
        )


# Mount all API routes under /api
app.include_router(api_router, prefix=settings.API_V1_STR)
