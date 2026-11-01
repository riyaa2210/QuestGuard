"""QueueGuard – FastAPI application entry-point."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.logging_config import configure_logging
from app.routers import endpoints, events, health, alerts

logger = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    from app.telemetry import configure_telemetry
    configure_telemetry(app)
    logger.info("queueguard_startup", env=settings.app_env, llm=settings.llm_enabled)
    yield
    logger.info("queueguard_shutdown")


app = FastAPI(
    title="QueueGuard",
    description=(
        "AI-assisted webhook reliability platform.\n\n"
        "Features: HMAC signing · circuit breaker · rate limiting · "
        "fan-out · JSON Schema validation · p50/p95/p99 latency stats · "
        "alert rules · OpenTelemetry tracing."
    ),
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handler ────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        method=request.method,
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred."},
    )


# ── Routers ─────────────────────────────────────────────────────────────────────
app.include_router(health.router, tags=["health"])
app.include_router(endpoints.router, prefix="/api/v1/endpoints", tags=["endpoints"])
app.include_router(events.router, prefix="/api/v1/events", tags=["events"])
app.include_router(alerts.router, prefix="/api/v1", tags=["alerts & stats & fanout"])
