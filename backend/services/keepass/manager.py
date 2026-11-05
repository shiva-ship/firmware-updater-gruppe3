"""Verwaltet hochgeladene KeePass-Datenbanken je Benutzersitzung.

Nach dem Entsperren wird ausschließlich die Metadaten-Baumstruktur im Speicher gehalten.
Das PyKeePass-Objekt (mit entschlüsselten Passwörtern) und das Masterpasswort werden
sofort verworfen. Spätere Funktionen (Geräte-APIs etc.) öffnen die Datei bei Bedarf erneut.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from backend.errors import DatabaseLimitReached, DatabaseLocked, DatabaseNotFound, InvalidDatabaseFile, InvalidMasterPassword

from .storage import UploadStorage
from .tree import GroupNode, build_tree

logger = logging.getLogger(__name__)


class DatabaseStatus(str, Enum):
    LOCKED = "locked"
    UNLOCKED = "unlocked"


@dataclass
class DatabaseHandle:
    id: str
    owner_session_id: str
    owner_user_id: int
    filename: str
    path: Path
    size_bytes: int
    uploaded_at: datetime
    status: DatabaseStatus = DatabaseStatus.LOCKED
    unlocked_at: datetime | None = None
    tree: GroupNode | None = None


def open_keepass(path: Path, master_password: str):
    """Öffnet eine KDBX-Datei. Übersetzt pykeepass-Fehler in fachliche Fehler."""
    from pykeepass import PyKeePass
    from pykeepass.exceptions import CredentialsError

    try:
        return PyKeePass(str(path), password=master_password)
    except CredentialsError:
        raise InvalidMasterPassword() from None
    except Exception as exc:  # beschädigte oder manipulierte Datei
        logger.info("KDBX-Datei konnte nicht gelesen werden (%s)", type(exc).__name__)
        raise InvalidDatabaseFile() from None


class KeePassSessionManager:
    def __init__(self, storage: UploadStorage, max_per_session: int) -> None:
        self._storage = storage
        self._max_per_session = max_per_session
        self._handles: dict[str, DatabaseHandle] = {}
        self._lock = threading.Lock()
        self._unlock_locks: dict[str, threading.Lock] = {}

    def register(self, *, session_id: str, user_id: int, filename: str, path: Path, size_bytes: int) -> DatabaseHandle:
        with self._lock:
            owned = sum(1 for h in self._handles.values() if h.owner_session_id == session_id)
            if owned >= self._max_per_session:
                self._storage.delete(path)
                raise DatabaseLimitReached()
            handle = DatabaseHandle(
                id=uuid.uuid4().hex,
                owner_session_id=session_id,
                owner_user_id=user_id,
                filename=filename,
                path=path,
                size_bytes=size_bytes,
                uploaded_at=datetime.now(timezone.utc),
            )
            self._handles[handle.id] = handle
            self._unlock_locks[handle.id] = threading.Lock()
        return handle

    def can_register(self, session_id: str) -> bool:
        with self._lock:
            return sum(1 for h in self._handles.values() if h.owner_session_id == session_id) < self._max_per_session

    def list_for(self, session_id: str, user_id: int) -> list[DatabaseHandle]:
        with self._lock:
            handles = [
                h for h in self._handles.values() if h.owner_session_id == session_id and h.owner_user_id == user_id
            ]
        return sorted(handles, key=lambda h: h.uploaded_at)

    def get(self, db_id: str, session_id: str, user_id: int) -> DatabaseHandle:
        with self._lock:
            handle = self._handles.get(db_id)
        # Fremde Datenbanken werden wie nicht vorhandene behandelt (keine Existenz-Leaks).
        if handle is None or handle.owner_session_id != session_id or handle.owner_user_id != user_id:
            raise DatabaseNotFound()
        return handle

    def refresh(self, db_id: str, session_id: str, user_id: int, master_password: str) -> DatabaseHandle:
        """Entschlüsselt die Datei (erneut) und ersetzt die Baumstruktur.
        Bei falschem Passwort bleibt ein bereits vorhandener Baum unverändert."""
        handle = self.get(db_id, session_id, user_id)
        lock = self._unlock_locks.get(db_id)
        if lock is None:
            raise DatabaseNotFound()
        with lock:
            kp = open_keepass(handle.path, master_password)
            try:
                tree = build_tree(kp)
            finally:
                del kp
            # Falls die Datenbank währenddessen geschlossen wurde:
            with self._lock:
                if db_id not in self._handles:
                    raise DatabaseNotFound()
                handle.tree = tree
                handle.status = DatabaseStatus.UNLOCKED
                handle.unlocked_at = datetime.now(timezone.utc)
        return handle

    def verify_master_password(self, db_id: str, session_id: str, user_id: int, master_password: str) -> None:
        """Reine Freigabeprüfung (z. B. künftig vor einem Firmwareupdate): öffnet die Datei,
        verwirft das Ergebnis sofort und wirft ``InvalidMasterPassword`` bei falschem Passwort."""
        handle = self.get(db_id, session_id, user_id)
        kp = open_keepass(handle.path, master_password)
        del kp

    def get_tree(self, db_id: str, session_id: str, user_id: int) -> tuple[DatabaseHandle, GroupNode]:
        handle = self.get(db_id, session_id, user_id)
        if handle.status is not DatabaseStatus.UNLOCKED or handle.tree is None:
            raise DatabaseLocked()
        return handle, handle.tree

    def close(self, db_id: str, session_id: str, user_id: int) -> None:
        handle = self.get(db_id, session_id, user_id)
        self._remove(handle.id)

    def close_all_for_session(self, session_id: str) -> int:
        with self._lock:
            ids = [h.id for h in self._handles.values() if h.owner_session_id == session_id]
        for db_id in ids:
            self._remove(db_id)
        return len(ids)

    def close_all(self) -> None:
        with self._lock:
            ids = list(self._handles)
        for db_id in ids:
            self._remove(db_id)

    def _remove(self, db_id: str) -> None:
        with self._lock:
            handle = self._handles.pop(db_id, None)
            self._unlock_locks.pop(db_id, None)
        if handle is not None:
            handle.tree = None
            self._storage.delete(handle.path)
