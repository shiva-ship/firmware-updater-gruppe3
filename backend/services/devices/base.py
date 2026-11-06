"""Gemeinsame Typen der Herstelleradapter.

Ein Adapter verbindet die Anwendung mit einem vorhandenen Python-Gerätetreiber im
Projektverzeichnis (``balluff_update.py``, ``firewall_update.py`` …). Der Adapter ist
also *nicht* die Firmware: Er ist der Treiber, der das Update technisch durchführt.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Protocol

from backend.config import PROJECT_ROOT
from backend.services.keepass import DeviceAccess

Vendor = Literal["balluff", "adstec", "siemens"]
ConnectionState = Literal["online", "offline", "error", "not_checked"]

VENDOR_LABELS: dict[str, str] = {
    "balluff": "Balluff IO-Link-Master",
    "adstec": "ads-tec Firewall / Router",
    "siemens": "Siemens SIMATIC SPS",
}


class DeviceError(Exception):
    """Fehler, bei dem das Gerät nachweislich *nicht* verändert wurde (z. B. Anmeldung fehlgeschlagen)."""


class CriticalDeviceError(Exception):
    """Fehler nach Beginn einer Änderung oder unbekannter Gerätezustand → gesamter Ablauf stoppt."""


@dataclass
class DeviceInfo:
    connection: ConnectionState
    installed_version: str | None = None
    model: str | None = None
    serial_number: str | None = None
    mac_address: str | None = None
    message: str | None = None
    simulated: bool = False
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class UpdateResult:
    previous_version: str | None
    message: str
    details: dict = field(default_factory=dict)


ProgressFn = Callable[[str, float], None]
"""Fortschritt melden: (Schrittbeschreibung, Anteil 0..1 innerhalb des Geräts)."""


class DeviceAdapter(Protocol):
    vendor: Vendor
    label: str
    driver_module: str
    firmware_suffixes: tuple[str, ...]
    supports_read: bool
    supports_update: bool
    # Darf das Update die Anlage anhalten (z. B. SPS STOP/RUN)? Dann ist eine gesonderte Freigabe nötig.
    requires_stop_run: bool
    notes: str

    def driver_available(self) -> tuple[bool, str | None]: ...

    def read_info(self, access: DeviceAccess) -> DeviceInfo: ...

    def update(self, access: DeviceAccess, firmware_path, target_version: str, progress: ProgressFn) -> UpdateResult: ...


def load_driver(module: str):
    """Importiert ein Treiber-Skript aus dem Projektverzeichnis."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    return importlib.import_module(module)


def check_driver(*modules: str) -> tuple[bool, str | None]:
    for module in modules:
        try:
            load_driver(module)
        except Exception as exc:  # fehlende Abhängigkeit (z. B. snap7) oder Syntaxfehler
            return False, f"{module}: {type(exc).__name__}: {exc}"[:300]
    return True, None
