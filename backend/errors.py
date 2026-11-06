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


class DeviceNotFound(AppError):
    status_code = 404
    code = "device_not_found"
    message = "Das Gerät wurde in der Datenbank nicht gefunden."


class DeviceIncomplete(AppError):
    status_code = 400
    code = "device_incomplete"
    message = "Im KeePass-Eintrag fehlen URL (oder Feld base_url), Benutzername oder Passwort."


class UnsupportedDevice(AppError):
    status_code = 400
    code = "unsupported_device"
    message = "Für dieses Gerät ist kein Firmwareupdate verfügbar. Unterstützt werden Balluff-Master und ads-tec-Firewalls."


class FirmwareFileNotFound(AppError):
    status_code = 400
    code = "firmware_file_not_found"
    message = "Die Firmware-Datei wurde nicht gefunden oder passt nicht zum Gerätetyp."


class FirmwareUpdateBusy(AppError):
    status_code = 409
    code = "firmware_update_busy"
    message = "Für dieses Gerät läuft bereits ein Firmwareupdate."


class FirmwareUpdateFailed(AppError):
    status_code = 502
    code = "firmware_update_failed"
    message = "Das Firmwareupdate ist fehlgeschlagen."
