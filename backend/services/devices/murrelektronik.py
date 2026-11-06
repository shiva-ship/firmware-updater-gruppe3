"""Adapter für den Murrelektronik IMPACT67 Pro PN (Art. 54630) auf Basis von ``murrelektronik.py``.

Der Treiber liest über die IO-Link-REST-API und aktualisiert über die HTTP-Aufrufe der
Geräte-Weboberfläche (``/netx/login``, ``/netx/firmware``, ``/netx/reset``). Details stehen in
``MURRELEKTRONIK_API.md``.
"""

from __future__ import annotations

from pathlib import Path

from backend.services.keepass import DeviceAccess

from .base import CriticalDeviceError, DeviceError, DeviceInfo, ProgressFn, UpdateResult, check_driver, load_driver
from .versions import compare_versions

DRIVER = "murrelektronik"


class MurrelektronikAdapter:
    vendor = "murrelektronik"
    label = "Murrelektronik IMPACT67 Pro PN"
    driver_module = DRIVER
    firmware_suffixes = (".m3z",)
    supports_read = True
    supports_update = True
    requires_stop_run = False
    notes = "IO-Link-REST-API zum Lesen, HTTP-Aufrufe der Weboberfläche für das Update (murrelektronik.py)."

    def __init__(self, timeout: float = 10, reboot_timeout: float = 900, poll_interval: float = 4) -> None:
        self.timeout = timeout
        self.reboot_timeout = reboot_timeout
        self.poll_interval = poll_interval

    def driver_available(self):
        return check_driver(DRIVER)

    def _driver(self, access: DeviceAccess, progress: ProgressFn | None = None):
        if not access.complete:
            raise DeviceError("Im KeePass-Eintrag fehlen URL (oder Feld base_url), Benutzername oder Passwort.")
        return load_driver(DRIVER).Impact67Driver(
            access.base_url,
            access.username,
            access.password,
            request_timeout=self.timeout,
            poll_interval=self.poll_interval,
            ready_timeout=self.reboot_timeout,
            progress=progress,
        )

    def read_info(self, access: DeviceAccess) -> DeviceInfo:
        try:
            info = self._driver(access).get_info()
        except DeviceError as exc:
            return DeviceInfo(connection="error", message=str(exc))
        return DeviceInfo(
            connection=info.state,
            installed_version=info.firmware,
            model=info.name,
            serial_number=info.serial,
            mac_address=info.mac,
            message=None if info.state == "online" else "IMPACT67 nicht erreichbar oder Antwort unbrauchbar.",
        )

    def update(self, access: DeviceAccess, firmware_path: Path, target_version: str, progress: ProgressFn) -> UpdateResult:
        driver = self._driver(access, progress)
        drv = load_driver(DRIVER)
        try:
            package = drv.read_package(str(firmware_path))
        except drv.FirmwareRejected as exc:
            raise DeviceError(str(exc)) from None
        if compare_versions(package.version, target_version) != 0:
            raise DeviceError(f"Paket enthält Version {package.version}, freigegeben ist {target_version}.")

        previous = driver.get_info().firmware
        result = driver.update(str(firmware_path))
        if result["status"] in ("ok", "already_up_to_date"):
            return UpdateResult(
                previous_version=previous,
                message="Firmware installiert und verifiziert.",
                details={"installed_version": result["version"], "reset": result.get("reset")},
            )
        if result.get("phase") == "precheck":
            raise DeviceError(result["detail"])
        raise CriticalDeviceError(f"{result['phase']}: {result['detail']}"[:300])
