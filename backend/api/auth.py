"""Anmeldung, Abmeldung und Sitzungsprüfung."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response, status

from backend.errors import InvalidCredentials, TooManyAttempts
from backend.services.auth import Session

from .deps import SESSION_COOKIE, Services, client_ip, get_services, require_csrf
from .schemas import LoginRequest, SessionOut, UserOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _session_out(session: Session) -> SessionOut:
    return SessionOut(
        authenticated=True,
        user=UserOut(id=session.user.id, username=session.user.username, role=session.user.role),
        csrf_token=session.csrf_token,
        expires_at=datetime.fromtimestamp(session.expires_at, tz=timezone.utc),
    )


def _set_session_cookie(response: Response, token: str, services: Services) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=services.settings.secure_cookies,
        samesite="strict",
        path="/",
        max_age=services.settings.session_absolute_hours * 3600,
    )


@router.post("/login", response_model=SessionOut)
def login(body: LoginRequest, request: Request, response: Response, services: Services = Depends(get_services)):
    username = body.username.strip()
    user_key = f"user:{username.casefold()}"
    ip_key = f"ip:{client_ip(request)}"

    retry_after = max(services.login_user_limiter.retry_after(user_key), services.login_ip_limiter.retry_after(ip_key))
    if retry_after > 0:
        raise TooManyAttempts(retry_after)

    user = services.users.authenticate(username, body.password.get_secret_value())
    if user is None:
        services.login_user_limiter.register_failure(user_key)
        services.login_ip_limiter.register_failure(ip_key)
        logger.info("Fehlgeschlagene Anmeldung von %s", client_ip(request))
        raise InvalidCredentials()

    services.login_user_limiter.reset(user_key)
    # Schutz vor Session Fixation: eine evtl. vorhandene alte Sitzung wird beendet.
    services.sessions.revoke(request.cookies.get(SESSION_COOKIE))
    token, session = services.sessions.create(user)
    _set_session_cookie(response, token, services)
    logger.info("Benutzer-ID %s angemeldet", user.id)
    return _session_out(session)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session: Session = Depends(require_csrf), services: Services = Depends(get_services)) -> Response:
    # Beendet die Sitzung; der Callback schließt alle KeePass-Datenbanken und löscht die Dateien.
    services.sessions.revoke_by_id(session.session_id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, path="/", secure=services.settings.secure_cookies, httponly=True, samesite="strict")
    return response


@router.get("/session", response_model=SessionOut)
def current_session(request: Request, response: Response, services: Services = Depends(get_services)):
    token = request.cookies.get(SESSION_COOKIE)
    session = services.sessions.get(token)
    if session is None:
        if token:
            response.delete_cookie(SESSION_COOKIE, path="/")
        return SessionOut(authenticated=False)
    return _session_out(session)
