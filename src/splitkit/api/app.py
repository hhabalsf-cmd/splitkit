"""Application factory: wires settings, connection pool, middleware and routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from psycopg_pool import ConnectionPool

from splitkit.api.envelope import fail, install_handlers
from splitkit.api.ratelimit import FixedWindowLimiter
from splitkit.api.repository import ExperimentRepository
from splitkit.api.routes import router
from splitkit.api.settings import Settings

UNLIMITED_PATHS = frozenset({"/health"})


def _client_id(request: Request, trusted_hops: int) -> str:
    """Client IP for rate limiting.

    Each trusted proxy appends the address it saw, so the real client is the
    `trusted_hops`-th entry from the right. Anything further left is
    client-supplied and must not be trusted (it would let callers dodge the
    limiter by rotating a fake header).
    """
    if trusted_hops > 0:
        parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(parts) >= trusted_hops:
            return parts[-trusted_hops]
    return request.client.host if request.client else "unknown"


def create_app(settings: Settings, pool: ConnectionPool | None = None) -> FastAPI:
    """Pass `pool` to share one (tests); otherwise the app owns its pool's lifecycle."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned = pool is None
        active = pool or ConnectionPool(
            settings.pg_dsn, min_size=1, max_size=settings.pool_max,
            kwargs={"autocommit": True}, open=True,
        )
        app.state.repo = ExperimentRepository(active)
        try:
            yield
        finally:
            if owned:
                active.close()

    app = FastAPI(title="Splitkit", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    limiter = FixedWindowLimiter(settings.rate_limit_per_min)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        client = _client_id(request, settings.trusted_proxy_hops)
        if request.url.path not in UNLIMITED_PATHS and not limiter.allow(client):
            return fail(429, "rate limit exceeded", headers={"Retry-After": "60"})
        return await call_next(request)

    if settings.cors_origins:
        # Browsers may call the public SDK routes; X-API-Key is not an allowed
        # header, so admin routes stay unreachable cross-origin.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["content-type"],
        )

    install_handlers(app)
    app.include_router(router)

    if settings.dashboard_dir:
        # Same origin as the API, so the admin key never crosses origins.
        # StaticFiles resolves paths inside the directory and rejects traversal.
        app.mount("/dashboard", StaticFiles(directory=settings.dashboard_dir, html=True), name="dashboard")

        @app.get("/", include_in_schema=False)
        def root() -> RedirectResponse:
            return RedirectResponse("/dashboard/", status_code=307)

    return app
