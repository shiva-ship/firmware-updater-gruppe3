"""Gemeinsame Abhängigkeiten: Dienste, Sitzung, CSRF."""

from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Depends, Request

from backend.config import Settings
from backend.errors import CsrfFailed, NotAuthenticated
from backend.services.auth import FailureRateLimiter, Session, SessionStore, UserRepository
from backend.services.keepass import KeePassSessionManager, UploadStorage

SESSION_COOKIE = "asm_session"
CSRF_HEADER = "X-CSRF-Token"


@dataclass
class Services:
    settings: Settings
    users: UserRepository
    sessions: SessionStore
    storage: UploadStorage
    keepass: KeePassSessionManager
    login_user_limiter: FailureRateLimiter
    login_ip_limiter: FailureRateLimiter
    unlock_limiter: FailureRateLimiter
    # Nur gesetzt, solange noch kein Benutzer existiert (Ersteinrichtung im Browser).
    setup_token: str | None = None


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_session(request: Request, services: Services = Depends(get_services)) -> Session:
    session = services.sessions.get(request.cookies.get(SESSION_COOKIE))
    if session is None:
        raise NotAuthenticated()
    return session


def require_csrf(request: Request, session: Session = Depends(get_session)) -> Session:
    """Synchronizer-Token: Das Token kennt nur das eigene Frontend (aus /api/auth/session)."""
    sent = request.headers.get(CSRF_HEADER, "")
    if not sent or not hmac.compare_digest(sent.encode(), session.csrf_token.encode()):
        raise CsrfFailed()
    return session


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
