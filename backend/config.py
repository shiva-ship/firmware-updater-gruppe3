"""Zentrale Konfiguration. Werte kommen aus Umgebungsvariablen (Präfix ``ASM_``) oder ``.env``."""

from __future__ import annotations

import ipaddress
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _default_data_dir() -> Path:
    """Benutzerprivates Datenverzeichnis außerhalb des Repositories."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "ADS-TEC-Security-Manager"
    return Path.home() / ".local" / "state" / "ads-tec-security-manager"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ASM_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["production", "development"] = "production"
    host: str = "127.0.0.1"
    port: int = 8000
    # Kommagetrennte Liste erlaubter Host-Header (Schutz gegen DNS-Rebinding).
    allowed_hosts: str = "127.0.0.1,localhost"

    data_dir: Path = Field(default_factory=_default_data_dir)
    frontend_dist: Path = PROJECT_ROOT / "frontend" / "dist"

    tls_certfile: Path | None = None
    tls_keyfile: Path | None = None
    # None = automatisch (Secure-Cookies genau dann, wenn TLS aktiv ist).
    cookie_secure: bool | None = None

    session_idle_minutes: int = Field(default=30, ge=1)
    session_absolute_hours: int = Field(default=8, ge=1)

    login_max_attempts: int = Field(default=5, ge=1)
    login_window_seconds: int = Field(default=900, ge=1)
    login_lockout_seconds: int = Field(default=900, ge=1)

    unlock_max_attempts: int = Field(default=5, ge=1)
    unlock_window_seconds: int = Field(default=300, ge=1)
    unlock_lockout_seconds: int = Field(default=300, ge=1)

    # Einmal-Schlüssel für die Ersteinrichtung im Browser (setzt start.ps1 automatisch).
    # Ohne Wert erzeugt der Server selbst einen und zeigt den Link in der Konsole an.
    setup_token: str | None = None

    max_upload_bytes: int = Field(default=20 * 1024 * 1024, ge=1024)
    max_databases_per_session: int = Field(default=5, ge=1)
    cleanup_interval_seconds: int = Field(default=60, ge=1)

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def tls_enabled(self) -> bool:
        return bool(self.tls_certfile and self.tls_keyfile)

    @property
    def secure_cookies(self) -> bool:
        return self.tls_enabled if self.cookie_secure is None else self.cookie_secure

    @property
    def allowed_host_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def users_db_path(self) -> Path:
        return self.data_dir / "users.sqlite3"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def binds_loopback_only(self) -> bool:
        if self.host == "localhost":
            return True
        try:
            return ipaddress.ip_address(self.host).is_loopback
        except ValueError:
            return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
