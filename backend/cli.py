"""Lokale Benutzerverwaltung über die Kommandozeile.

Beispiele (PowerShell, im Projektverzeichnis mit aktivierter venv):
    python -m backend.cli create-admin --username admin
    python -m backend.cli reset-password --username admin
    python -m backend.cli list-users
    python -m backend.cli deactivate --username alter.admin

Passwörter werden ausschließlich interaktiv und verdeckt abgefragt (nie als Argument),
damit sie nicht in der Shell-Historie landen.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from backend.config import get_settings
from backend.db import Database
from backend.services.auth import UserError, UserRepository
from backend.services.auth.passwords import MIN_PASSWORD_LENGTH


def _repo() -> UserRepository:
    settings = get_settings()
    db = Database(settings.users_db_path)
    db.init_schema()
    return UserRepository(db)


def _prompt_password() -> str:
    if not sys.stdin.isatty():
        print("Fehler: Passwortabfrage benötigt ein interaktives Terminal.", file=sys.stderr)
        raise SystemExit(2)
    print(
        f"Passwortrichtlinie: mindestens {MIN_PASSWORD_LENGTH} Zeichen, "
        "mindestens drei Zeichenklassen (a-z, A-Z, 0-9, Sonderzeichen)."
    )
    first = getpass.getpass("Neues Passwort: ")
    second = getpass.getpass("Passwort wiederholen: ")
    if first != second:
        print("Fehler: Die Passwörter stimmen nicht überein.", file=sys.stderr)
        raise SystemExit(1)
    return first


def _username(value: str | None) -> str:
    return (value or input("Benutzername: ")).strip()


def cmd_create_admin(args: argparse.Namespace) -> int:
    repo = _repo()
    username = _username(args.username)
    if repo.get_by_username(username):
        print(f"Fehler: Der Benutzer '{username}' existiert bereits.", file=sys.stderr)
        return 1
    password = _prompt_password()
    try:
        user = repo.create_user(username, password, role="admin")
    except UserError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    print(f"Administrator '{user.username}' wurde angelegt.")
    return 0


def cmd_ensure_admin(_: argparse.Namespace) -> int:
    """Legt beim ersten Start interaktiv einen Administrator an, falls noch keiner existiert."""
    if _repo().count() > 0:
        return 0
    print("Erster Start: Es ist noch kein Benutzer vorhanden. Bitte Administrator anlegen.")
    while True:
        args = argparse.Namespace(username=None)
        if cmd_create_admin(args) == 0:
            return 0
        print("Bitte erneut versuchen.\n")


def cmd_reset_password(args: argparse.Namespace) -> int:
    repo = _repo()
    username = _username(args.username)
    if not repo.get_by_username(username):
        print(f"Fehler: Der Benutzer '{username}' existiert nicht.", file=sys.stderr)
        return 1
    try:
        repo.set_password(username, _prompt_password())
    except UserError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    print(f"Passwort für '{username}' wurde geändert. Bestehende Sitzungen wurden beendet.")
    return 0


def cmd_set_active(args: argparse.Namespace, active: bool) -> int:
    try:
        _repo().set_active(_username(args.username), active)
    except UserError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    print("Benutzer aktiviert." if active else "Benutzer deaktiviert, Sitzungen beendet.")
    return 0


def cmd_list_users(_: argparse.Namespace) -> int:
    users = _repo().list_users()
    if not users:
        print("Keine Benutzer vorhanden. Legen Sie einen Administrator mit 'create-admin' an.")
        return 0
    for user in users:
        state = "aktiv" if user.is_active else "deaktiviert"
        print(f"{user.id:>4}  {user.username:<32} {user.role:<8} {state}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.cli", description="ADS-TEC Security Manager – Benutzerverwaltung")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-admin", help="Administrator anlegen")
    p.add_argument("--username")
    p.set_defaults(func=cmd_create_admin)

    p = sub.add_parser("ensure-admin", help="Administrator anlegen, falls noch keiner existiert")
    p.set_defaults(func=cmd_ensure_admin)

    p = sub.add_parser("reset-password", help="Passwort eines Benutzers setzen")
    p.add_argument("--username")
    p.set_defaults(func=cmd_reset_password)

    p = sub.add_parser("deactivate", help="Benutzer deaktivieren")
    p.add_argument("--username")
    p.set_defaults(func=lambda a: cmd_set_active(a, False))

    p = sub.add_parser("activate", help="Benutzer aktivieren")
    p.add_argument("--username")
    p.set_defaults(func=lambda a: cmd_set_active(a, True))

    p = sub.add_parser("list-users", help="Benutzer auflisten")
    p.set_defaults(func=cmd_list_users)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
