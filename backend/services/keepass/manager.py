"""Verwaltet hochgeladene KeePass-Datenbanken je Benutzersitzung.

Nach dem Entsperren werden die Metadaten-Baumstruktur und die geschwärzten Notizen im Speicher
gehalten. Das Masterpasswort und das PyKeePass-Objekt werden sofort verworfen.

Die Login-Daten der angezeigten Geräte werden zusätzlich für ``credential_ttl`` Sekunden nur im
Arbeitsspeicher zwischengespeichert, damit Vorbereiten und Freigabe ohne erneute Eingabe des
Masterpassworts möglich sind. Sie werden nie auf die Festplatte geschrieben und beim Schließen
der Datei, beim Abmelden, nach Ablauf der Frist oder beim Serverende gelöscht.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from backend.errors import (
    DatabaseLimitReached,
    DatabaseLocked,
    DatabaseNotFound,
    InvalidDatabaseFile,
    InvalidMasterPassword,
)

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
    # Geschwärzte Notizen je Eintrags-UUID: (Text, wurde geschwärzt)
    notes: dict[str, tuple[str, bool]] = field(default_factory=dict)
    # Zwischengespeicherte Login-Daten (nur RAM) und Ablaufzeitpunkt (time.monotonic)
    access: dict[str, "DeviceAccess"] = field(default_factory=dict, repr=False)
    access_until: float = 0.0


@dataclass(frozen=True)
class DeviceAccess:
    """Zugangsdaten für den Gerätetreiber. Nur im Backend, nie im Frontend oder im Log.
    Benutzername/Passwort dürfen fehlen (z. B. SPS ohne Anmeldung) – der Treiber prüft selbst."""

    entry_id: str
    title: str
    base_url: str
    username: str = ""
    password: str = field(default="", repr=False)
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return bool(self.base_url and self.username and self.password)


def access_from_entry(entry) -> DeviceAccess:
    custom = entry.custom_properties or {}
    return DeviceAccess(
        entry_id=str(entry.uuid),
        title=entry.title or "",
        base_url=(custom.get("base_url") or entry.url or "").strip(),
        username=entry.username or "",
        password=entry.password or "",
        extra={k: str(v) for k, v in custom.items() if k.casefold() in {"rack", "slot"} and v is not None},
    )


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
    def __init__(self, storage: UploadStorage, max_per_session: int, credential_ttl: float = 1800, clock=time.monotonic) -> None:
        self._storage = storage
        self._credential_ttl = credential_ttl
        self._clock = clock
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
            notes: dict[str, tuple[str, bool]] = {}
            try:
                tree = build_tree(kp, notes)
                # Login-Daten nur für die angezeigten Geräte zwischenspeichern
                shown = {e.id for e, _ in tree.iter_entries_with_path()}
                access = {str(e.uuid): access_from_entry(e) for e in kp.entries if str(e.uuid) in shown}
            finally:
                del kp
            # Falls die Datenbank währenddessen geschlossen wurde:
            with self._lock:
                if db_id not in self._handles:
                    raise DatabaseNotFound()
                handle.tree = tree
                handle.notes = notes
                handle.access = access
                handle.access_until = self._clock() + self._credential_ttl
                handle.status = DatabaseStatus.UNLOCKED
                handle.unlocked_at = datetime.now(timezone.utc)
        return handle

    def verify_master_password(self, db_id: str, session_id: str, user_id: int, master_password: str) -> None:
        """Prüft das Masterpasswort serverseitig (wirft InvalidMasterPassword)."""
        handle = self.get(db_id, session_id, user_id)
        kp = open_keepass(handle.path, master_password)
        del kp

    def cached_access(self, db_id: str, session_id: str, user_id: int, entry_ids: list[str]) -> dict[str, DeviceAccess] | None:
        """Zwischengespeicherte Login-Daten, oder None, wenn die Frist abgelaufen ist."""
        handle = self.get(db_id, session_id, user_id)
        with self._lock:
            if not handle.access or handle.access_until <= self._clock():
                handle.access = {}
                return None
            return {i: handle.access[i] for i in entry_ids if i in handle.access}

    def purge_expired_access(self) -> None:
        now = self._clock()
        with self._lock:
            for handle in self._handles.values():
                if handle.access and handle.access_until <= now:
                    handle.access = {}

    def read_device_access(
        self, db_id: str, session_id: str, user_id: int, master_password: str, entry_ids: list[str]
    ) -> dict[str, DeviceAccess]:
        """Liest die Zugangsdaten mehrerer Einträge in einem Durchgang. Unbekannte IDs fehlen im Ergebnis."""
        handle = self.get(db_id, session_id, user_id)
        kp = open_keepass(handle.path, master_password)
        result: dict[str, DeviceAccess] = {}
        try:
            for entry_id in entry_ids:
                try:
                    entry_uuid = uuid.UUID(entry_id)
                except ValueError:
                    continue
                entry = kp.find_entries(uuid=entry_uuid, first=True)
                if entry is not None:
                    result[entry_id] = access_from_entry(entry)
        finally:
            del kp
        return result

    def get_notes(self, db_id: str, session_id: str, user_id: int, entry_id: str) -> tuple[str, bool] | None:
        handle, _ = self.get_tree(db_id, session_id, user_id)
        return handle.notes.get(entry_id)

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
            handle.notes = {}
            handle.access = {}
            self._storage.delete(handle.path)
