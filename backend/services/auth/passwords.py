"""Passwort-Hashing ausschließlich mit Argon2id."""

from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024

# Parameter orientieren sich an OWASP-Empfehlungen für Argon2id (64 MiB, t=3).
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

# Wird verwendet, wenn ein Benutzer nicht existiert, damit die Antwortzeit
# keine Rückschlüsse auf vorhandene Benutzernamen zulässt.
_DUMMY_HASH = _hasher.hash("timing-equalization-placeholder")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def equalize_timing(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


def password_policy_violations(password: str, username: str | None = None) -> list[str]:
    problems: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Mindestens {MIN_PASSWORD_LENGTH} Zeichen erforderlich.")
    if len(password) > MAX_PASSWORD_LENGTH:
        problems.append(f"Höchstens {MAX_PASSWORD_LENGTH} Zeichen erlaubt.")
    if password.strip() != password:
        problems.append("Keine führenden oder abschließenden Leerzeichen.")
    if username and username.casefold() in password.casefold():
        problems.append("Das Passwort darf den Benutzernamen nicht enthalten.")
    classes = sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if classes < 3:
        problems.append("Mindestens drei der Zeichenklassen Kleinbuchstaben, Großbuchstaben, Ziffern, Sonderzeichen.")
    return problems
