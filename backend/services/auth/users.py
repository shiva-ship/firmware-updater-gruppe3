"""Benutzerverwaltung auf Basis von SQLite."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.db import Database

from . import passwords

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,64}$")


class UserError(ValueError):
    pass


@dataclass(frozen=True)
class User:
    id: int
    username: str
    role: str
    is_active: bool


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_user(row: sqlite3.Row) -> User:
    return User(id=row["id"], username=row["username"], role=row["role"], is_active=bool(row["is_active"]))


class UserRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create_user(self, username: str, password: str, role: str = "admin") -> User:
        if not USERNAME_PATTERN.fullmatch(username):
            raise UserError("Benutzername: 3–64 Zeichen, erlaubt sind A–Z, a–z, 0–9, '.', '_' und '-'.")
        problems = passwords.password_policy_violations(password, username)
        if problems:
            raise UserError(" ".join(problems))
        password_hash = passwords.hash_password(password)
        try:
            with self._db.connect() as conn:
                cur = conn.execute(
                    "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                    (username, password_hash, role, _now_iso()),
                )
                user_id = cur.lastrowid
        except sqlite3.IntegrityError as exc:
            raise UserError(f"Der Benutzer '{username}' existiert bereits.") from exc
        return User(id=int(user_id), username=username, role=role, is_active=True)

    def set_password(self, username: str, password: str) -> None:
        problems = passwords.password_policy_violations(password, username)
        if problems:
            raise UserError(" ".join(problems))
        with self._db.connect() as conn:
            cur = conn.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?",
                (passwords.hash_password(password), username),
            )
            if cur.rowcount == 0:
                raise UserError(f"Der Benutzer '{username}' existiert nicht.")
            # Bestehende Sitzungen werden bei Passwortänderung ungültig.
            conn.execute(
                "DELETE FROM sessions WHERE user_id = (SELECT id FROM users WHERE username = ?)", (username,)
            )

    def set_active(self, username: str, active: bool) -> None:
        with self._db.connect() as conn:
            cur = conn.execute("UPDATE users SET is_active = ? WHERE username = ?", (int(active), username))
            if cur.rowcount == 0:
                raise UserError(f"Der Benutzer '{username}' existiert nicht.")
            if not active:
                conn.execute(
                    "DELETE FROM sessions WHERE user_id = (SELECT id FROM users WHERE username = ?)", (username,)
                )

    def authenticate(self, username: str, password: str) -> User | None:
        """Prüft Zugangsdaten mit konstantem Zeitverhalten. Gibt None bei Fehlschlag zurück."""
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            passwords.equalize_timing(password)
            return None
        if not passwords.verify_password(row["password_hash"], password):
            return None
        if not row["is_active"]:
            return None
        with self._db.connect() as conn:
            updates: dict[str, str] = {"last_login_at": _now_iso()}
            if passwords.needs_rehash(row["password_hash"]):
                updates["password_hash"] = passwords.hash_password(password)
            assignments = ", ".join(f"{column} = ?" for column in updates)
            conn.execute(f"UPDATE users SET {assignments} WHERE id = ?", (*updates.values(), row["id"]))
        return _row_to_user(row)

    def get_by_username(self, username: str) -> User | None:
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return _row_to_user(row) if row else None

    def list_users(self) -> list[User]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
        return [_row_to_user(r) for r in rows]

    def count(self) -> int:
        with self._db.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
