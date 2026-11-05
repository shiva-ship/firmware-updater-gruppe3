"""Serverseitige Sitzungen.

Das Cookie enthält nur ein zufälliges Token; in der Datenbank liegt lediglich dessen
SHA-256-Hash. Der Hash dient intern als Sitzungs-ID (z. B. zur Zuordnung von KeePass-Datenbanken).
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

from backend.db import Database

from .users import User


@dataclass(frozen=True)
class Session:
    session_id: str
    user: User
    csrf_token: str
    created_at: float
    expires_at: float


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()


class SessionStore:
    def __init__(
        self,
        db: Database,
        *,
        idle_seconds: int,
        absolute_seconds: int,
        on_session_end: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._db = db
        self._idle = idle_seconds
        self._absolute = absolute_seconds
        self._on_end = on_session_end
        self._clock = clock

    def create(self, user: User) -> tuple[str, Session]:
        token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        now = self._clock()
        absolute = now + self._absolute
        expires = min(now + self._idle, absolute)
        session_id = _hash_token(token)
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id_hash, user_id, csrf_token, created_at, last_seen_at, expires_at, absolute_expires_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, user.id, csrf_token, now, now, expires, absolute),
            )
        return token, Session(session_id, user, csrf_token, now, expires)

    def get(self, token: str | None) -> Session | None:
        """Liefert die gültige Sitzung und verlängert das Idle-Timeout (Sliding Expiration)."""
        if not token or len(token) > 128:
            return None
        session_id = _hash_token(token)
        now = self._clock()
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT s.*, u.username, u.role, u.is_active FROM sessions s"
                " JOIN users u ON u.id = s.user_id WHERE s.id_hash = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            if row["expires_at"] <= now or row["absolute_expires_at"] <= now or not row["is_active"]:
                conn.execute("DELETE FROM sessions WHERE id_hash = ?", (session_id,))
                expired = True
            else:
                expired = False
                expires = min(now + self._idle, row["absolute_expires_at"])
                conn.execute(
                    "UPDATE sessions SET last_seen_at = ?, expires_at = ? WHERE id_hash = ?",
                    (now, expires, session_id),
                )
        if expired:
            self._notify_end(session_id)
            return None
        user = User(id=row["user_id"], username=row["username"], role=row["role"], is_active=True)
        return Session(session_id, user, row["csrf_token"], row["created_at"], expires)

    def revoke(self, token: str | None) -> None:
        if not token or len(token) > 128:
            return
        self.revoke_by_id(_hash_token(token))

    def revoke_by_id(self, session_id: str) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE id_hash = ?", (session_id,))
        self._notify_end(session_id)

    def purge_expired(self) -> list[str]:
        now = self._clock()
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT id_hash FROM sessions WHERE expires_at <= ? OR absolute_expires_at <= ?", (now, now)
            ).fetchall()
            ids = [r["id_hash"] for r in rows]
            conn.executemany("DELETE FROM sessions WHERE id_hash = ?", [(i,) for i in ids])
        for session_id in ids:
            self._notify_end(session_id)
        return ids

    def active_session_ids(self) -> set[str]:
        with self._db.connect() as conn:
            return {r["id_hash"] for r in conn.execute("SELECT id_hash FROM sessions").fetchall()}

    def revoke_all(self) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM sessions")

    def _notify_end(self, session_id: str) -> None:
        if self._on_end is not None:
            self._on_end(session_id)
