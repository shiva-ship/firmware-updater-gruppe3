"""Adapter für Siemens-SPS (python-snap7), Grundlage ``Siemens_PLC.py``.

Nur lesend: CPU-Typ, Seriennummer und Firmwarestand (Order-Code V1.V2.V3).
Es existiert **kein** Firmware-Update-Treiber für die SPS. Das vorhandene Skript kann die
SPS nur in STOP/RUN versetzen – das wird von dieser Anwendung bewusst nie ausgeführt.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from backend.services.keepass import DeviceAccess

from .base import DeviceError, DeviceInfo, check_driver

DEFAULT_RACK = 0
DEFAULT_SLOT = 1


def _text(value) -> str | None:
    if isinstance(value, bytes):
        value = value.decode("ascii", "ignore")
    text = str(value or "").strip("\x00 ").strip()
    return text or None


class SiemensAdapter:
    vendor = "siemens"
    label = "Siemens SIMATIC SPS"
    driver_module = "snap7"
    firmware_suffixes: tuple[str, ...] = ()
    supports_read = True
    supports_update = False
    requires_stop_run = True
    notes = "Nur Statusabfrage (snap7). Kein Firmware-Update-Treiber vorhanden; STOP/RUN wird nie automatisch ausgelöst."

    def driver_available(self):
        return check_driver("snap7")

    def read_info(self, access: DeviceAccess) -> DeviceInfo:
        try:
            import snap7
        except ImportError:
            return DeviceInfo(connection="error", message="python-snap7 ist nicht installiert.")
        raw = access.base_url or ""
        host = urlsplit(raw if "://" in raw else f"tcp://{raw}").hostname
        if not host:
            return DeviceInfo(connection="error", message="Im KeePass-Eintrag fehlt die IP-Adresse der SPS.")
        try:
            rack = int(access.extra.get("rack", DEFAULT_RACK))
            slot = int(access.extra.get("slot", DEFAULT_SLOT))
        except ValueError:
            raise DeviceError("Rack/Slot im KeePass-Eintrag sind keine Zahlen.") from None
        plc = snap7.client.Client()
        try:
            plc.connect(host, rack, slot)
            info = plc.get_cpu_info()
            order = plc.get_order_code()
            version = f"V{order.V1}.{order.V2}.{order.V3}"
            return DeviceInfo(
                connection="online",
                installed_version=version,
                model=_text(getattr(info, "ModuleTypeName", None)) or _text(getattr(order, "OrderCode", None)),
                serial_number=_text(getattr(info, "SerialNumber", None)),
            )
        except Exception as exc:
            return DeviceInfo(connection="offline", message=f"SPS nicht erreichbar oder PUT/GET gesperrt: {exc}"[:300])
        finally:
            try:
                if plc.get_connected():
                    plc.disconnect()
            except Exception:
                pass

    def update(self, *_args, **_kwargs):
        raise DeviceError("Für Siemens-SPS ist kein Firmware-Update-Treiber vorhanden.")
