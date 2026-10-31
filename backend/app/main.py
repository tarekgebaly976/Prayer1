import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.api.routers import (
    admin,
    assets,
    attachments,
    auth,
    dashboard,
    inventory,
    io,
    kpi,
    lubrication,
    notifications,
    pdm,
    pm,
    shifts,
    shutdowns,
    workorders,
)
from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.core.errors import DomainError
from app.core.logging import configure_logging
from app.services.common import sync_rbac

log = logging.getLogger("cmms.api")
API = "/api/v1"


class RateLimiter:
    """Per-process sliding-window limiter keyed by client IP. Behind multiple replicas, also configure
    rate limiting at the load balancer / WAF (documented in SECURITY.md)."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and q[0] < now - 60:
            q.popleft()
        if len(q) >= self.per_minute:
            return False
        q.append(now)
        if len(self.hits) > 50000:
            self.hits.clear()
        return True


def create_app() -> FastAPI:
    configure_logging()
    s = get_settings()
    docs = s.environment != "production"
    app = FastAPI(
        title="PlantPulse API",
        version="0.1.0",
        docs_url=f"{API}/docs" if docs else None,
        redoc_url=None,
        openapi_url=f"{API}/openapi.json" if docs else None,
    )
    limiter = RateLimiter(s.rate_limit_per_minute)
    login_limiter = RateLimiter(s.login_rate_limit_per_minute)

    if s.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-CSRF-Token", "X-Plant-Id"],
        )

    @app.middleware("http")
    async def middleware(request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        ip = request.client.host if request.client else "?"
        path = request.url.path
        if path.startswith(API) and not path.startswith(f"{API}/health"):
            lim = login_limiter if path == f"{API}/auth/login" else limiter
            if not lim.allow(ip):
                return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429, headers={"Retry-After": "60"})
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error", extra={"request_id": rid, "path": path, "method": request.method})
            response = JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)
        dur = round((time.perf_counter() - start) * 1000, 1)
        response.headers["X-Request-Id"] = rid
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Cache-Control", "no-store")
        if s.cookie_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if path.startswith(API) and not path.startswith(f"{API}/docs"):
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if path != f"{API}/health/live":
            log.info(
                "request",
                extra={"request_id": rid, "path": path, "method": request.method, "status": response.status_code, "duration_ms": dur},
            )
        return response

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, e: DomainError) -> JSONResponse:
        return JSONResponse({"detail": e.message, "code": e.code}, status_code=e.status_code)

    @app.exception_handler(StaleDataError)
    async def stale(_: Request, e: StaleDataError) -> JSONResponse:
        return JSONResponse({"detail": "Record was modified concurrently; reload and retry", "code": "stale"}, status_code=409)

    @app.exception_handler(IntegrityError)
    async def integrity(_: Request, e: IntegrityError) -> JSONResponse:
        log.warning("integrity error: %s", str(e.orig)[:300])
        return JSONResponse(
            {"detail": "Conflicts with existing data (duplicate or invalid reference)", "code": "integrity"}, status_code=409
        )

    @app.exception_handler(RequestValidationError)
    async def validation(_: Request, e: RequestValidationError) -> JSONResponse:
        errs = [{"loc": list(x.get("loc", [])), "msg": x.get("msg"), "type": x.get("type")} for x in e.errors()]
        return JSONResponse({"detail": errs}, status_code=422)

    @app.get(f"{API}/health/live", tags=["health"])
    def live() -> dict:
        return {"status": "ok"}

    @app.get(f"{API}/meta", tags=["health"])
    def meta() -> dict:
        """Public facts the sign-in page needs before anyone is logged in."""
        return {"instance_label": get_settings().instance_label}

    @app.get(f"{API}/health/ready", tags=["health"])
    def ready() -> JSONResponse:
        checks = {}
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
                checks["database"] = "ok"
                ver = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
                checks["migration"] = ver
        except Exception as e:  # noqa: BLE001
            checks["database"] = f"error: {type(e).__name__}"
        ok = checks.get("database") == "ok"
        return JSONResponse({"status": "ok" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)

    for r in (
        auth.router,
        admin.router,
        assets.router,
        workorders.router,
        pm.router,
        lubrication.router,
        shifts.router,
        inventory.router,
        pdm.router,
        pdm.gateway,
        shutdowns.router,
        kpi.router,
        notifications.router,
        attachments.router,
        io.router,
        dashboard.router,
    ):
        app.include_router(r, prefix=API)

    @app.on_event("startup")
    def _startup() -> None:
        try:
            with SessionLocal() as db, db.begin():
                sync_rbac(db)
        except Exception:  # noqa: BLE001 - app still serves health checks; readiness reports DB state
            log.exception("RBAC sync failed at startup")

    return app


app = create_app()
