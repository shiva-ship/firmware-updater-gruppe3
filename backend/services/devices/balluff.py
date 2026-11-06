"""Adapter für Balluff-IO-Link-Master auf Basis von ``balluff_update.py`` / ``balluff_version.py``.

Verwendete REST-Endpunkte (alle aus den vorhandenen Skripten):
``POST /users/login``, ``GET /identification``, ``GET /firmwares``, ``GET /firmwares/{id}``,
``POST /firmwares/{id}/upload``, ``POST /firmwares/{id}/install``, ``POST /firmwares/{id}/reboot``.
"""

from __future__ import annotations

import time
from pathlib import Path

from backend.services.keepass import DeviceAccess

from .base import CriticalDeviceError, DeviceError, DeviceInfo, ProgressFn, UpdateResult, check_driver, load_driver
from .versions import compare_versions

DRIVER = "balluff_update"


def _find_value(data, *needles: str) -> str | None:
    """Sucht in der Identifikationsantwort nach einem Schlüssel, der einen der Begriffe enthält.
    Die genaue Struktur der Antwort ist geräteabhängig, daher bewusst tolerant."""
    if isinstance(data, dict):
        for key, value in data.items():
            folded = str(key).casefold()
            if any(n in folded for n in needles) and isinstance(value, (str, int)) and str(value).strip():
                return str(value).strip()
        for value in data.values():
            found = _find_value(value, *needles)
            if found:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _find_value(value, *needles)
            if found:
                return found
    return None


class BalluffAdapter:
    vendor = "balluff"
    label = "Balluff IO-Link-Master"
    driver_module = DRIVER
    firmware_suffixes = (".bff",)
    supports_read = True
    supports_update = True
    requires_stop_run = False
    notes = "REST-API des Masters: Upload, Installation und Neustart über balluff_update.py."

    def __init__(self, timeout: float = 10, reboot_timeout: float = 900, poll_interval: float = 5) -> None:
        self.timeout = timeout
        self.reboot_timeout = reboot_timeout
        self.poll_interval = poll_interval

    def driver_available(self):
        return check_driver(DRIVER)

    def _session(self, access: DeviceAccess):
        import requests

        drv = load_driver(DRIVER)
        if not access.complete:
            raise DeviceError("Im KeePass-Eintrag fehlen URL (oder Feld base_url), Benutzername oder Passwort.")
        zugang = drv.Zugang(drv.normalisiere_url(access.base_url), access.username, access.password)
        session = requests.Session()
        session.verify = False  # Master nutzt ein selbstsigniertes Zertifikat
        drv.login(session, zugang)
        return drv, zugang, session

    def _installed_version(self, drv, session, base_url: str) -> tuple[str, str | None]:
        firmware_id = drv.firmware_id_ermitteln(session, base_url)
        response = session.get(f"{base_url}/firmwares/{firmware_id}", timeout=self.timeout)
        response.raise_for_status()
        version = response.json().get("version")
        return firmware_id, str(version) if version is not None else None

    def read_info(self, access: DeviceAccess) -> DeviceInfo:
        import requests

        try:
            drv, zugang, session = self._session(access)
            with session:
                response = session.get(f"{zugang.base_url}/identification", timeout=self.timeout)
                response.raise_for_status()
                ident = response.json()
                _, version = self._installed_version(drv, session, zugang.base_url)
        except DeviceError as exc:
            return DeviceInfo(connection="error", message=str(exc))
        except requests.HTTPError as exc:
            return DeviceInfo(connection="error", message=f"HTTP {exc.response.status_code} vom Master")
        except (requests.ConnectionError, requests.Timeout):
            return DeviceInfo(connection="offline", message="Master nicht erreichbar.")
        except (ValueError, RuntimeError) as exc:
            return DeviceInfo(connection="error", message=str(exc)[:300])
        return DeviceInfo(
            connection="online",
            installed_version=version,
            model=_find_value(ident, "productname", "product", "ordercode", "devicename"),
            serial_number=_find_value(ident, "serial"),
            mac_address=_find_value(ident, "mac"),
        )

    def update(self, access: DeviceAccess, firmware_path: Path, target_version: str, progress: ProgressFn) -> UpdateResult:
        import requests

        # Phase 1 – nur lesend. Fehler hier verändern das Gerät nicht.
        progress("Anmeldung am Master", 0.05)
        try:
            drv, zugang, session = self._session(access)
            _, previous = self._installed_version(drv, session, zugang.base_url)
        except DeviceError:
            raise
        except Exception as exc:
            raise DeviceError(f"Vorprüfung fehlgeschlagen: {exc}"[:300]) from None

        # Phase 2 – ab hier wird das Gerät verändert. Jeder Fehler ⇒ unbekannter Zustand.
        progress("Firmware wird übertragen und installiert", 0.2)
        try:
            with session:
                result = drv.firmware_update(session, zugang, firmware_path)
        except Exception as exc:
            raise CriticalDeviceError(f"Fehler während Upload/Installation: {exc}"[:300]) from None

        progress("Warten auf Neustart des Masters", 0.6)
        deadline = time.monotonic() + self.reboot_timeout
        time.sleep(min(self.poll_interval * 2, self.reboot_timeout))
        current = None
        while time.monotonic() < deadline:
            try:
                drv2, zugang2, session2 = self._session(access)
                with session2:
                    _, current = self._installed_version(drv2, session2, zugang2.base_url)
                break
            except (requests.RequestException, RuntimeError, ValueError, DeviceError):
                time.sleep(self.poll_interval)
        if current is None:
            raise CriticalDeviceError("Master ist nach dem Update nicht wieder erreichbar – Zustand unbekannt.")

        progress("Installierte Firmware wird verifiziert", 0.9)
        if compare_versions(current, target_version) != 0:
            raise CriticalDeviceError(
                f"Verifikation fehlgeschlagen: Master meldet {current}, erwartet {target_version}."
            )
        return UpdateResult(previous_version=previous, message=str(result.get("message", "Firmware installiert.")),
                            details={"installed_version": current})
