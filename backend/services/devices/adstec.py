"""Adapter für ads-tec-Firewalls/Router auf Basis von ``firewall_update.py`` und ``jsonrpcdevice.py``.

Verwendet ausschließlich vorhandene Funktionen: ``status("imageversion")``,
``status("boot_finished")``, ``check_host`` und ``firewall_update.update_device`` (Upload über
``/priv/script/php_rpc/upload.php``). Seriennummer und MAC liest der vorhandene Treiber nicht
aus – sie werden daher nicht vom Gerät bestätigt.
"""

from __future__ import annotations

import time
from pathlib import Path

from backend.services.keepass import DeviceAccess

from .base import CriticalDeviceError, DeviceError, DeviceInfo, ProgressFn, UpdateResult, check_driver, load_driver
from .versions import compare_versions

DRIVERS = ("jsonrpcdevice", "firewall_update")


class AdstecAdapter:
    vendor = "adstec"
    label = "ads-tec Firewall / Router"
    driver_module = "firewall_update"
    firmware_suffixes = (".bin",)
    supports_read = True
    supports_update = True
    requires_stop_run = False
    notes = "JSON-RPC (jsonrpcdevice.py): Firmware-Upload, anschließend automatischer Neustart."

    def __init__(self, timeout: float = 10, reboot_timeout: float = 900, poll_interval: float = 3) -> None:
        self.timeout = timeout
        self.reboot_timeout = reboot_timeout
        self.poll_interval = poll_interval

    def driver_available(self):
        return check_driver(*DRIVERS)

    def _device(self, access: DeviceAccess):
        if not access.complete:
            raise DeviceError("Im KeePass-Eintrag fehlen URL (oder Feld base_url), Benutzername oder Passwort.")
        rpc = load_driver("jsonrpcdevice")
        fw = load_driver("firewall_update")
        host = fw.host_aus_url(access.base_url)
        return rpc, fw, host, rpc.AdstecJSONRPCDevice(host, access.username, access.password, timeout=self.timeout)

    def read_info(self, access: DeviceAccess) -> DeviceInfo:
        import requests

        try:
            _, _, _, dev = self._device(access)
            version = dev.status("imageversion")
        except DeviceError as exc:
            return DeviceInfo(connection="error", message=str(exc))
        except (requests.ConnectionError, requests.Timeout):
            return DeviceInfo(connection="offline", message="Firewall nicht erreichbar.")
        except Exception as exc:  # jsonrpcdevice wirft generische Exceptions (z. B. falsches Passwort)
            return DeviceInfo(connection="error", message=str(exc)[:300])
        return DeviceInfo(connection="online", installed_version=str(version) if version is not None else None)

    def _wait_for_reboot(self, rpc, host: str, access: DeviceAccess) -> str:
        """Begrenzte Variante von ``jsonrpcdevice.wait_for_reboot`` (die vorhandene wartet unbegrenzt)."""
        deadline = time.monotonic() + self.reboot_timeout
        went_offline = False
        while time.monotonic() < deadline:
            online, _ = rpc.check_host(host, timeout=5)
            if not online:
                went_offline = True
            elif went_offline:
                try:
                    dev = rpc.AdstecJSONRPCDevice(host, access.username, access.password, timeout=self.timeout)
                    if dev.status("boot_finished") == "yes":
                        return str(dev.status("imageversion"))
                except Exception:
                    pass
            time.sleep(self.poll_interval)
        if not went_offline:
            raise CriticalDeviceError("Die Firewall hat nicht neu gestartet – Zustand unbekannt.")
        raise CriticalDeviceError("Die Firewall ist nach dem Neustart nicht wieder bereit – Zustand unbekannt.")

    def update(self, access: DeviceAccess, firmware_path: Path, target_version: str, progress: ProgressFn) -> UpdateResult:
        progress("Anmeldung an der Firewall", 0.05)
        try:
            rpc, fw, host, dev = self._device(access)
            previous = dev.status("imageversion")
        except DeviceError:
            raise
        except Exception as exc:
            raise DeviceError(f"Vorprüfung fehlgeschlagen: {exc}"[:300]) from None

        progress("Firmware wird übertragen", 0.2)
        try:
            result = fw.update_device(access.base_url, access.username, access.password, firmware_path)
        except Exception as exc:
            raise CriticalDeviceError(f"Fehler beim Firmware-Upload: {exc}"[:300]) from None

        progress("Warten auf Neustart der Firewall", 0.55)
        current = self._wait_for_reboot(rpc, host, access)

        progress("Installierte Firmware wird verifiziert", 0.9)
        if compare_versions(current, target_version) != 0:
            raise CriticalDeviceError(f"Verifikation fehlgeschlagen: Firewall meldet {current}, erwartet {target_version}.")
        return UpdateResult(
            previous_version=str(previous) if previous is not None else None,
            message="Firmware installiert, Firewall neu gestartet und verifiziert.",
            details={"installed_version": current, "upload_result": str(result.get("upload_result", ""))[:200]},
        )
