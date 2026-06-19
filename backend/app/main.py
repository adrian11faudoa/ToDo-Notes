"""
app/main.py
───────────
FastAPI application factory.
Registers all routers, middleware, CORS, lifespan events.
"""

from __future__ import annotations
import logging
import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from prometheus_client import make_asgi_app, Counter, Histogram

from app.core.config import get_settings
from app.db.session import engine

settings = get_settings()
logger = structlog.get_logger(__name__)

# ── Prometheus metrics ────────────────────────────────────────────
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)


# ── Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown logic."""
    from app.utils.logging import configure_logging
    configure_logging()

    logger.info("NoteFlow API starting", env=settings.ENVIRONMENT)

    # Sentry
    if settings.SENTRY_DSN:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            integrations=[FastApiIntegration()],
            traces_sample_rate=0.1,
        )

    yield

    # Graceful shutdown — close Redis and DB pool
    logger.info("NoteFlow API shutting down")
    from app.services.cache_service import cache_service
    await cache_service.close()
    await engine.dispose()


# ── Application factory ───────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="NoteFlow API",
        description="Offline-first Notes & Tasks — now on AWS",
        version=settings.APP_VERSION,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=86400,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # ── Request timing + metrics middleware ───────────────────────
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        path = request.url.path
        REQUEST_COUNT.labels(
            method=request.method, path=path, status=response.status_code
        ).inc()
        REQUEST_LATENCY.labels(method=request.method, path=path).observe(duration)

        response.headers["X-Response-Time"] = f"{duration:.4f}"
        return response

    # ── Request ID middleware ─────────────────────────────────────
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        import uuid
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # ── Exception handlers ────────────────────────────────────────
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Validation error",
                "errors": exc.errors(),
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    # ── Routers ───────────────────────────────────────────────────
    from app.api.routes.auth import router as auth_router
    from app.api.routes.notes import router as notes_router
    from app.api.routes.tasks import router as tasks_router, projects_router
    from app.api.routes.pomodoro import router as pomodoro_router
    from app.api.routes.folders import (
        folders_router, tags_router, search_router,
        stats_router, health_router,
    )

    prefix = settings.API_V1_PREFIX
    app.include_router(health_router)                           # /health, /ready
    app.include_router(auth_router,     prefix=prefix)          # /api/v1/auth
    app.include_router(notes_router,    prefix=prefix)          # /api/v1/notes
    app.include_router(tasks_router,    prefix=prefix)          # /api/v1/tasks
    app.include_router(projects_router, prefix=prefix)          # /api/v1/projects
    app.include_router(folders_router,  prefix=prefix)          # /api/v1/folders
    app.include_router(tags_router,     prefix=prefix)          # /api/v1/tags
    app.include_router(search_router,   prefix=prefix)          # /api/v1/search
    app.include_router(stats_router,    prefix=prefix)          # /api/v1/stats
    app.include_router(pomodoro_router, prefix=prefix)          # /api/v1/pomodoro

    # Prometheus metrics endpoint (scrape internally only)
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    return app


app = create_app()
