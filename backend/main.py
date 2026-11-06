"""FastAPI-Anwendung: Verdrahtung von Diensten, Sicherheits-Middleware und Frontend-Auslieferung."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend import __version__
from backend.api import api_router
from backend.api.deps import Services
from backend.config import Settings, get_settings
from backend.db import Database
from backend.errors import AppError
from backend.services.auth import FailureRateLimiter, SessionStore, UserRepository
from backend.services.firmware import FirmwareUpdater
from backend.services.devices import DemoSimulator, default_adapters
from backend.services.keepass import KeePassSessionManager, UploadStorage
from backend.services.updates import UpdateService

logger = logging.getLogger("backend")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)


def build_services(settings: Settings) -> Services:
    db = Database(settings.users_db_path)
    storage = UploadStorage(settings.upload_dir)
    keepass = KeePassSessionManager(storage, settings.max_databases_per_session, settings.credential_ttl_seconds)
    firmware = FirmwareUpdater(settings.firmware_dir, settings.firmware_manifest_path)
    updates = UpdateService(
        mode=settings.device_mode,
        keepass=keepass,
        firmware=firmware,
        adapters=default_adapters(settings.device_timeout_seconds, settings.reboot_timeout_seconds),
        simulator=DemoSimulator(settings.demo_step_seconds),
        plan_ttl_seconds=settings.plan_ttl_seconds,
        authorization_ttl_seconds=settings.authorization_ttl_seconds,
        credential_ttl_seconds=settings.credential_ttl_seconds,
    )

    def on_session_end(session_id: str) -> None:
        updates.forget_session(session_id)
        keepass.close_all_for_session(session_id)

    sessions = SessionStore(
        db,
        idle_seconds=settings.session_idle_minutes * 60,
        absolute_seconds=settings.session_absolute_hours * 3600,
        on_session_end=on_session_end,
    )
    return Services(
        settings=settings,
        users=UserRepository(db),
        sessions=sessions,
        storage=storage,
        keepass=keepass,
        login_user_limiter=FailureRateLimiter(
            settings.login_max_attempts, settings.login_window_seconds, settings.login_lockout_seconds
        ),
        # Pro IP großzügiger, damit mehrere Benutzer hinter einer Adresse arbeiten können.
        login_ip_limiter=FailureRateLimiter(
            settings.login_max_attempts * 4, settings.login_window_seconds, settings.login_lockout_seconds
        ),
        unlock_limiter=FailureRateLimiter(
            settings.unlock_max_attempts, settings.unlock_window_seconds, settings.unlock_lockout_seconds
        ),
        firmware=firmware,
        updates=updates,
    )


def _error_response(status_code: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status_code, headers=headers)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    services = build_services(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        services.settings.data_dir.mkdir(parents=True, exist_ok=True)
        Database(settings.users_db_path).init_schema()
        services.storage.prepare()
        logger.info("Gerätemodus: %s", "LIVE – Zugriff auf das Industrienetz" if settings.device_mode == "live" else "DEMO – simulierte Geräte, keine Geräteänderungen")
        # Nach einem Neustart existieren keine In-Memory-Datenbanksitzungen mehr:
        # verwaiste Uploads löschen und alte Anmeldesitzungen beenden.
        removed = services.storage.wipe()
        services.sessions.revoke_all()
        if removed:
            logger.info("%d verwaiste temporäre Datei(en) entfernt", removed)
        if services.users.count() == 0:
            services.setup_token = settings.setup_token or secrets.token_urlsafe(24)
            if not settings.setup_token:
                # Bewusst nur auf die Konsole, nicht ins Log.
                scheme = "https" if settings.tls_enabled else "http"
                print(
                    "\n  Ersteinrichtung: Öffnen Sie diesen Link, um den Administrator anzulegen:\n"
                    f"  {scheme}://127.0.0.1:{settings.port}/#setup={services.setup_token}\n",
                    flush=True,
                )

        async def cleanup_loop() -> None:
            while True:
                await asyncio.sleep(settings.cleanup_interval_seconds)
                try:
                    expired = await run_in_threadpool(services.sessions.purge_expired)
                    if expired:
                        logger.info("%d abgelaufene Sitzung(en) beendet", len(expired))
                except Exception:
                    logger.exception("Fehler bei der Sitzungsbereinigung")

        task = asyncio.create_task(cleanup_loop())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            services.keepass.close_all()

    app = FastAPI(
        title="ADS-TEC Security Manager",
        version=__version__,
        lifespan=lifespan,
        debug=False,
        docs_url="/api/docs" if settings.is_development else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.is_development else None,
    )
    app.state.services = services

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Die Standardantwort von FastAPI enthält die Eingabewerte – das würde z. B. ein
        # (zu langes) Masterpasswort zurücksenden. Daher nur Feldpfade, keine Werte.
        fields = sorted({".".join(str(p) for p in err.get("loc", ()) if p != "body") for err in exc.errors()})
        return JSONResponse(
            {"error": {"code": "validation_error", "message": "Ungültige Eingabe.", "fields": fields}},
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = "Nicht gefunden." if exc.status_code == 404 else "Anfrage fehlgeschlagen."
        return _error_response(exc.status_code, f"http_{exc.status_code}", message)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.error("Unerwarteter Fehler: %s", type(exc).__name__)
        return _error_response(500, "internal_error", "Interner Serverfehler.")

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        # Zusätzlicher CSRF-Schutz: Cross-Origin-Requests mit unsicheren Methoden ablehnen.
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin and origin != "null":
                if urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower():
                    return _error_response(403, "origin_rejected", "Anfrage von fremder Herkunft abgelehnt.")
            elif origin == "null":
                return _error_response(403, "origin_rejected", "Anfrage von fremder Herkunft abgelehnt.")

        response = await call_next(request)
        headers = response.headers
        headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["Referrer-Policy"] = "no-referrer"
        headers["Cross-Origin-Opener-Policy"] = "same-origin"
        headers["Cross-Origin-Resource-Policy"] = "same-origin"
        headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        if request.url.path.startswith("/api/"):
            headers["Cache-Control"] = "no-store"
            headers["Pragma"] = "no-cache"
        if settings.tls_enabled:
            headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)
    app.include_router(api_router)

    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    else:
        logger.warning("Frontend-Build nicht gefunden (%s). Nur die API ist verfügbar.", settings.frontend_dist)

    return app
