"""Fachliche Fehler mit stabilen Fehlercodes für das Frontend.

Fehlermeldungen enthalten niemals Benutzereingaben (Passwörter, Dateiinhalte).
"""

from __future__ import annotations


class AppError(Exception):
    status_code: int = 400
    code: str = "bad_request"
    message: str = "Ungültige Anfrage."

    def __init__(self, message: str | None = None, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message
        self.headers = headers or {}


class NotAuthenticated(AppError):
    status_code = 401
    code = "not_authenticated"
    message = "Bitte melden Sie sich an."


class InvalidCredentials(AppError):
    status_code = 401
    code = "invalid_credentials"
    message = "Benutzername oder Passwort ist falsch."


class TooManyAttempts(AppError):
    status_code = 429
    code = "too_many_attempts"
    message = "Zu viele Fehlversuche. Bitte warten Sie, bevor Sie es erneut versuchen."

    def __init__(self, retry_after: float) -> None:
        seconds = max(1, int(retry_after + 0.999))
        super().__init__(headers={"Retry-After": str(seconds)})
        self.retry_after = seconds


class CsrfFailed(AppError):
    status_code = 403
    code = "csrf_failed"
    message = "Die Anfrage konnte nicht verifiziert werden. Bitte laden Sie die Seite neu."


class DatabaseNotFound(AppError):
    status_code = 404
    code = "database_not_found"
    message = "Die Datenbank wurde nicht gefunden oder bereits geschlossen."


class InvalidDatabaseFile(AppError):
    status_code = 400
    code = "invalid_database_file"
    message = "Die Datei ist keine gültige KeePass-Datenbank (KDBX)."


class FileTooLarge(AppError):
    status_code = 413
    code = "file_too_large"
    message = "Die Datei überschreitet die maximal erlaubte Größe."


class InvalidMasterPassword(AppError):
    # Bewusst nicht 401: Die Anmeldung am Security Manager bleibt gültig.
    status_code = 400
    code = "invalid_master_password"
    message = "Das Masterpasswort ist falsch."


class DatabaseLocked(AppError):
    status_code = 409
    code = "database_locked"
    message = "Die Datenbank ist noch nicht entsperrt."


class DatabaseLimitReached(AppError):
    status_code = 409
    code = "database_limit_reached"
    message = "Maximale Anzahl gleichzeitig geöffneter Datenbanken erreicht. Bitte schließen Sie zuerst eine Datenbank."
