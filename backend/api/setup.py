"""Ersteinrichtung im Browser: Anlegen des ersten Administrators.

Nur möglich, solange kein Benutzer existiert, und nur mit dem Einmal-Schlüssel, den
der lokale Starter dem Browser im URL-Fragment (#setup=…) mitgibt. Das Fragment wird
nie an den Server übertragen oder protokolliert; der Schlüssel kommt nur im Request-Body.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field, SecretStr

from backend.errors import AppError, TooManyAttempts
from backend.services.auth import UserError
from backend.services.auth.passwords import MIN_PASSWORD_LENGTH

from .auth import _session_out, _set_session_cookie
from .deps import Services, client_ip, get_services
from .schemas import SessionOut, StrictModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/setup", tags=["setup"])


class SetupNotAvailable(AppError):
    status_code = 409
    code = "setup_not_available"
    message = "Die Einrichtung ist bereits abgeschlossen. Bitte melden Sie sich an."


class InvalidSetupToken(AppError):
    status_code = 403
    code = "invalid_setup_token"
    message = "Ungültiger Einrichtungsschlüssel. Bitte starten Sie die Anwendung über start.cmd."


class InvalidUserInput(AppError):
    status_code = 400
    code = "invalid_user_input"


class SetupRequest(StrictModel):
    setup_token: SecretStr = Field(min_length=1, max_length=256)
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=1024)


def _setup_required(services: Services) -> bool:
    if services.setup_token and services.users.count() > 0:
        services.setup_token = None  # z. B. per CLI angelegt
    return services.setup_token is not None


@router.get("/status")
def setup_status(services: Services = Depends(get_services)) -> dict:
    return {"setup_required": _setup_required(services), "min_password_length": MIN_PASSWORD_LENGTH}


@router.post("", response_model=SessionOut)
def complete_setup(body: SetupRequest, request: Request, response: Response, services: Services = Depends(get_services)):
    if not _setup_required(services):
        raise SetupNotAvailable()
    ip_key = f"setup:{client_ip(request)}"
    retry_after = services.login_ip_limiter.retry_after(ip_key)
    if retry_after > 0:
        raise TooManyAttempts(retry_after)

    expected = services.setup_token or ""
    if not hmac.compare_digest(body.setup_token.get_secret_value().encode(), expected.encode()):
        services.login_ip_limiter.register_failure(ip_key)
        raise InvalidSetupToken()

    try:
        user = services.users.create_user(body.username.strip(), body.password.get_secret_value(), role="admin")
    except UserError as exc:
        raise InvalidUserInput(str(exc)) from None

    services.setup_token = None
    logger.info("Ersteinrichtung abgeschlossen, Administrator-ID %s angelegt", user.id)
    token, session = services.sessions.create(user)
    _set_session_cookie(response, token, services)
    return _session_out(session)
