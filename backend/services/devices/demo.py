"""DEMO-Modus: simulierte Geräteinformationen auf Basis der echten KeePass-Einträge.

Der Simulator importiert keinen Gerätetreiber und öffnet keine Netzwerkverbindung.
Alle Werte sind deterministisch aus der KeePass-UUID abgeleitet und als simuliert gekennzeichnet.
"""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

from backend.services.keepass import DeviceNode

from .base import DeviceError, DeviceInfo, ProgressFn, UpdateResult

_VERSIONS = {
    "adstec": ("2.3.1", "2.3.2", "2.3.4"),
    "balluff": ("1.4.2", "1.5.0", "1.6.1"),
    "siemens": ("V4.5.2", "V4.6.1"),
}
_MODELS = {"adstec": "IRF3xxx", "balluff": "BNI IO-Link-Master", "siemens": "S7-1200"}

UPDATE_STEPS = (
    ("Anmeldung am Gerät (simuliert)", 0.05),
    ("Firmware wird übertragen (simuliert)", 0.25),
    ("Firmware wird installiert (simuliert)", 0.5),
    ("Warten auf Neustart (simuliert)", 0.7),
    ("Installierte Firmware wird verifiziert (simuliert)", 0.9),
)


def _seed(entry_id: str) -> bytes:
    return hashlib.sha256(f"asm-demo:{entry_id}".encode()).digest()


class DemoSimulator:
    def __init__(self, step_seconds: float = 0.8) -> None:
        self.step_seconds = step_seconds
        self._installed: dict[str, str] = {}
        self._lock = threading.Lock()

    def read_info(self, node: DeviceNode) -> DeviceInfo:
        seed = _seed(node.id)
        vendor = node.device_type
        if vendor is None:
            return DeviceInfo(connection="not_checked", simulated=True, message="Hersteller nicht erkannt (simuliert).")
        if seed[0] % 9 == 0:
            return DeviceInfo(connection="offline", simulated=True, message="Gerät nicht erreichbar (simuliert).")
        with self._lock:
            installed = self._installed.get(node.id)
        if installed is None:
            options = _VERSIONS[vendor]
            installed = options[seed[1] % len(options)]
        return DeviceInfo(
            connection="online",
            installed_version=installed,
            model=node.model or _MODELS[vendor],
            serial_number=node.serial_number,
            mac_address=node.mac_address or "02:AD:" + ":".join(f"{b:02X}" for b in seed[2:6]),
            simulated=True,
            message="Simulierte Geräteinformation (DEMO-Modus).",
        )

    def update(self, node: DeviceNode, _firmware_path: Path, target_version: str, progress: ProgressFn) -> UpdateResult:
        info = self.read_info(node)
        if info.connection != "online":
            raise DeviceError("Gerät nicht erreichbar (simuliert) – keine Änderung.")
        for label, fraction in UPDATE_STEPS:
            progress(label, fraction)
            time.sleep(self.step_seconds)
        with self._lock:
            self._installed[node.id] = target_version
        return UpdateResult(
            previous_version=info.installed_version,
            message="Update simuliert – am Gerät wurde nichts verändert.",
            details={"installed_version": target_version, "simulated": True},
        )
