"""KeePass-Datenbanken: Upload, Entsperren, Baumstruktur, Schließen."""

from __future__ import annotations

import logging
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Request, Response, status
from starlette.concurrency import run_in_threadpool

from backend.errors import DatabaseLimitReached, FileTooLarge, InvalidDatabaseFile, InvalidMasterPassword, TooManyAttempts
from backend.services.auth import Session
from backend.services.keepass import DatabaseHandle, sanitize_display_name, tree_stats

from .deps import Services, get_services, get_session, require_csrf
from .schemas import DatabaseListOut, DatabaseOut, TreeOut, UnlockRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/databases", tags=["databases"])

FILENAME_HEADER = "X-File-Name"


def _db_out(handle: DatabaseHandle) -> DatabaseOut:
    return DatabaseOut(
        id=handle.id,
        filename=handle.filename,
        size_bytes=handle.size_bytes,
        status=handle.status.value,
        uploaded_at=handle.uploaded_at,
        unlocked_at=handle.unlocked_at,
    )


@router.get("", response_model=DatabaseListOut)
def list_databases(session: Session = Depends(get_session), services: Services = Depends(get_services)):
    handles = services.keepass.list_for(session.session_id, session.user.id)
    return DatabaseListOut(
        databases=[_db_out(h) for h in handles],
        max_upload_bytes=services.settings.max_upload_bytes,
        max_databases=services.settings.max_databases_per_session,
    )


@router.post("", response_model=DatabaseOut, status_code=status.HTTP_201_CREATED)
async def upload_database(
    request: Request, session: Session = Depends(require_csrf), services: Services = Depends(get_services)
):
    """Der Dateiinhalt wird als ``application/octet-stream`` gesendet und direkt (ohne Zwischen-
    speicherung im System-Temp) in den geschützten Upload-Bereich gestreamt."""
    filename = sanitize_display_name(unquote(request.headers.get(FILENAME_HEADER, "")))
    if not filename.lower().endswith(".kdbx"):
        raise InvalidDatabaseFile("Bitte wählen Sie eine Datei mit der Endung .kdbx.")

    max_bytes = services.settings.max_upload_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise FileTooLarge()
    if not services.keepass.can_register(session.session_id):
        raise DatabaseLimitReached()

    path, size = await services.storage.save_stream(request.stream(), max_bytes)
    handle = services.keepass.register(
        session_id=session.session_id, user_id=session.user.id, filename=filename, path=path, size_bytes=size
    )
    logger.info("KDBX-Datei hochgeladen (%d Bytes) von Benutzer-ID %s", size, session.user.id)
    return _db_out(handle)


@router.post("/{db_id}/refresh", response_model=DatabaseOut)
async def refresh_database(
    db_id: str, body: UnlockRequest, session: Session = Depends(require_csrf), services: Services = Depends(get_services)
):
    # Eigentumsprüfung vor dem Rate-Limit, damit fremde IDs nicht unterscheidbar sind.
    services.keepass.get(db_id, session.session_id, session.user.id)
    key = f"unlock:{session.user.id}:{db_id}"
    retry_after = services.unlock_limiter.retry_after(key)
    if retry_after > 0:
        raise TooManyAttempts(retry_after)
    try:
        # KDF (Argon2/AES-KDF) ist rechenintensiv → Thread-Pool, damit der Server reaktionsfähig bleibt.
        handle = await run_in_threadpool(
            services.keepass.refresh, db_id, session.session_id, session.user.id, body.master_password.get_secret_value()
        )
    except InvalidMasterPassword:
        services.unlock_limiter.register_failure(key)
        raise
    services.unlock_limiter.reset(key)
    return _db_out(handle)


@router.get("/{db_id}/tree", response_model=TreeOut)
def get_tree(db_id: str, session: Session = Depends(get_session), services: Services = Depends(get_services)):
    handle, root = services.keepass.get_tree(db_id, session.session_id, session.user.id)
    return TreeOut(database=_db_out(handle), root=root.to_dict(), stats=tree_stats(root))


@router.delete("/{db_id}", status_code=status.HTTP_204_NO_CONTENT)
def close_database(db_id: str, session: Session = Depends(require_csrf), services: Services = Depends(get_services)):
    services.keepass.close(db_id, session.session_id, session.user.id)
    services.updates.forget_database(session.session_id, db_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
