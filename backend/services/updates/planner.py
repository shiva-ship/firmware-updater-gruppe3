"""Erstellt aus ausgewählten Geräten einen geprüften Updateplan (reine Funktion, ohne Gerätezugriff).

Je Gerät werden nacheinander geprüft: Identität (Seriennummer), Treiber, Verbindung,
installierte Version, Firmwarepaket, Integrität, Kompatibilität, Versionsvergleich und eine
evtl. nötige STOP/RUN-Freigabe. Nur Geräte mit Status ``ready`` werden später ausgeführt.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import asdict, dataclass, field
from typing import Literal

from backend.services.devices import VENDOR_LABELS, DeviceInfo, compare_versions, parse_version
from backend.services.firmware import FirmwarePackage
from backend.services.keepass import DeviceNode

CheckStatus = Literal["ok", "warn", "fail", "skip"]
ItemStatus = Literal["ready", "up_to_date", "blocked", "no_driver"]

# Standard-Reihenfolge: Feldgeräte zuerst, Netzwerkinfrastruktur zuletzt – deren Neustart
# würde sonst die Verbindung zu den dahinterliegenden Geräten unterbrechen.
VENDOR_PRIORITY = {"balluff": 100, "siemens": 200, "adstec": 900}
UNKNOWN_PRIORITY = 500

EFFECTS = {
    "balluff": [
        "Der IO-Link-Master startet nach der Installation neu.",
        "Angeschlossene IO-Link-Geräte liefern während des Neustarts keine Prozessdaten.",
    ],
    "adstec": [
        "Die Firewall startet nach dem Upload neu.",
        "Netzwerkverbindungen über dieses Gerät sind während des Neustarts unterbrochen.",
        "Wird deshalb nach allen anderen Geräten aktualisiert.",
    ],
    "siemens": ["Ein Firmwareupdate würde die SPS in STOP versetzen und die Anlage anhalten."],
}


@dataclass(frozen=True)
class AdapterCapabilities:
    vendor: str
    label: str
    driver_module: str
    supports_update: bool
    driver_available: bool
    driver_error: str | None = None
    requires_stop_run: bool = False


@dataclass
class Check:
    key: str
    label: str
    status: CheckStatus
    message: str


@dataclass
class PlanItem:
    entry_id: str
    title: str
    path: list[str]
    vendor: str | None
    vendor_label: str
    serial_number: str | None
    serial_status: str
    host: str | None
    model: str | None
    installed_version: str | None
    target_version: str | None
    package: str | None
    package_sha256: str | None
    driver_module: str | None
    status: ItemStatus
    checks: list[Check]
    effects: list[str]
    order_key: int
    order_reason: str
    simulated: bool
    position: int = 0
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


_TOKEN_SPLIT = re.compile(r"[\s,;/()_\-]+")


def check_model(package: FirmwarePackage, device_model: str | None, keepass_model: str | None,
                title: str, firmware_string: str | None) -> tuple[bool | None, str]:
    """Prüft das Gerätemodell gegen die freigegebenen Modelle des Pakets.

    Reihenfolge: Modell vom Gerät → KeePass-Feld ``Model`` → Eintragsname → Firmwarestring.
    Ein ausdrücklich bekanntes Modell (Gerät oder KeePass) entscheidet allein. Sonst genügt ein
    passendes Wort im Eintragsnamen oder Firmwarestring. Ohne Treffer: nicht prüfbar (None)."""
    if not package.models:
        return True, "alle Modelle des Herstellers"
    patterns = [p.casefold() for p in package.models]

    def matches(text: str) -> bool:
        return any(fnmatch.fnmatchcase(text.casefold(), p) for p in patterns)

    for source, model in (("Gerät", device_model), ("KeePass-Feld Model", keepass_model)):
        if model:
            return matches(model), f"Modell {model} ({source})"
    for source, text in (("Eintragsname", title), ("Firmwarestring", firmware_string)):
        for token in _TOKEN_SPLIT.split(text or ""):
            if token and matches(token):
                return True, f"Modell {token} ({source})"
    return None, "Modell unbekannt – bitte im KeePass-Eintrag das Feld „Model“ ergänzen"


def _select_package(vendor: str, model: str | None, packages: list[FirmwarePackage]):
    """Liefert (Paket, Fehlermeldung). Bevorzugt die höchste freigegebene, kompatible Version."""
    own = [p for p in packages if p.vendor == vendor]
    if not own:
        return None, "Kein lokales Firmwarepaket für diesen Hersteller im Ordner „Firmware“."
    released = [p for p in own if p.status == "released"]
    if not released:
        if any(p.status == "hash_mismatch" for p in own):
            return None, "Prüfsumme des Pakets weicht von der Freigabe ab – Datei wurde verändert."
        return None, "Firmwarepaket ist nicht freigegeben (Version, Modelle und Prüfsumme fehlen)."
    compatible = [p for p in released if not p.models or p.model_compatible(model) is not False]
    if not compatible:
        return released[0], None  # Inkompatibilität wird in der Kompatibilitätsprüfung gemeldet
    return max(compatible, key=lambda p: parse_version(p.version) or ()), None


def plan_item(
    node: DeviceNode,
    path: tuple[str, ...],
    info: DeviceInfo | None,
    adapter: AdapterCapabilities | None,
    packages: list[FirmwarePackage],
    *,
    simulated: bool,
) -> PlanItem:
    checks: list[Check] = []

    def add(key: str, label: str, status: CheckStatus, message: str) -> None:
        checks.append(Check(key, label, status, message))

    vendor = node.device_type
    priority = node.update_order if node.update_order is not None else VENDOR_PRIORITY.get(vendor or "", UNKNOWN_PRIORITY)
    order_reason = (
        f"KeePass-Feld UpdateOrder = {node.update_order}"
        if node.update_order is not None
        else {
            "balluff": "Feldgerät – vor der Netzwerkinfrastruktur",
            "siemens": "Steuerung – nach den Feldgeräten",
            "adstec": "Netzwerkinfrastruktur – zuletzt",
        }.get(vendor or "", "Standardreihenfolge")
    )
    item = PlanItem(
        entry_id=node.id,
        title=node.title,
        path=list(path),
        vendor=vendor,
        vendor_label=VENDOR_LABELS.get(vendor or "", "Unbekannter Hersteller"),
        serial_number=node.serial_number,
        serial_status=node.serial_status,
        host=node.host,
        model=(info.model if info and info.model else node.model),
        installed_version=info.installed_version if info else None,
        target_version=None,
        package=None,
        package_sha256=None,
        driver_module=adapter.driver_module if adapter else None,
        status="blocked",
        checks=checks,
        effects=list(EFFECTS.get(vendor or "", [])),
        order_key=priority,
        order_reason=order_reason,
        simulated=simulated,
    )

    # 1. Identität
    if node.serial_status == "ok":
        add("identity", "Geräteidentität", "ok", f"Seriennummer {node.serial_number} ist eindeutig.")
    elif node.serial_status == "duplicate":
        add("identity", "Geräteidentität", "fail",
            f"Seriennummer {node.serial_number} ist mehrfach vergeben – keine automatische Zuordnung.")
    else:
        add("identity", "Geräteidentität", "fail", "Keine Seriennummer hinterlegt – keine automatische Zuordnung.")
    if info and info.serial_number and node.serial_number:
        if info.serial_number.strip().casefold() == node.serial_number.strip().casefold():
            add("identity_device", "Seriennummer am Gerät", "ok", "Gerät meldet dieselbe Seriennummer.")
        else:
            add("identity_device", "Seriennummer am Gerät", "fail",
                f"Gerät meldet {info.serial_number}, KeePass enthält {node.serial_number}.")
    elif info and info.connection == "online":
        add("identity_device", "Seriennummer am Gerät", "warn", "Der Treiber kann die Seriennummer nicht auslesen – nicht vom Gerät bestätigt.")

    # 2. Treiber
    if vendor is None:
        add("driver", "Update-Treiber", "fail", "Hersteller nicht erkannt – kein Treiber zuordenbar.")
        item.status = "no_driver"
    elif adapter is None or not adapter.supports_update:
        add("driver", "Update-Treiber", "fail", "Für diesen Gerätetyp ist kein Firmware-Update-Treiber vorhanden.")
        item.status = "no_driver"
    elif not adapter.driver_available:
        add("driver", "Update-Treiber", "fail", f"Treiber kann nicht geladen werden: {adapter.driver_error}")
    else:
        add("driver", "Update-Treiber", "ok", f"{adapter.driver_module}.py")
    if item.status == "no_driver":
        _finish(item)
        return item

    # 3. Verbindung & installierte Version
    if info is None or info.connection == "not_checked":
        add("connection", "Verbindung", "fail", "Gerät wurde noch nicht geprüft.")
    elif info.connection != "online":
        add("connection", "Verbindung", "fail", info.message or "Gerät nicht erreichbar.")
    else:
        add("connection", "Verbindung", "ok", "Simuliert erreichbar." if simulated else "Gerät erreichbar.")
    if info and info.connection == "online":
        if info.installed_version:
            add("installed", "Installierte Firmware", "ok", info.installed_version)
        else:
            add("installed", "Installierte Firmware", "fail", "Version konnte nicht ausgelesen werden – Zustand nicht verifizierbar.")

    # 4. Paket, Integrität, Kompatibilität
    package, problem = _select_package(vendor, item.model, packages)
    if package is None:
        add("package", "Firmwarepaket", "fail", problem or "Kein Paket.")
    else:
        item.package = package.name
        item.package_sha256 = package.sha256
        item.target_version = package.version
        add("package", "Firmwarepaket", "ok", f"{package.name} (Version {package.version})")
        if package.vendor_checksum_verified:
            add("integrity", "Integrität", "ok", "SHA-256 stimmt mit der Hersteller-Prüfsumme überein.")
        else:
            add("integrity", "Integrität", "warn",
                "SHA-256 stimmt mit der lokalen Freigabe überein; keine Hersteller-Prüfsumme hinterlegt.")
        models = ", ".join(package.models) if package.models else "alle Modelle des Herstellers"
        compatible, detail = check_model(
            package, info.model if info else None, node.model, node.title, info.installed_version if info else None
        )
        if compatible is True:
            add("compatibility", "Kompatibilität", "ok", f"Freigegeben für {models} · {detail}.")
        elif compatible is None:
            add("compatibility", "Kompatibilität", "fail", f"{detail}. Paket ist nur für {models} freigegeben.")
        else:
            add("compatibility", "Kompatibilität", "fail", f"{detail} passt nicht zu {models}.")

        # 5. Versionsvergleich
        if info and info.installed_version:
            cmp = compare_versions(info.installed_version, package.version)
            if cmp is None:
                add("version", "Versionsvergleich", "fail", "Versionen sind nicht vergleichbar.")
            elif cmp == 0:
                add("version", "Versionsvergleich", "ok", "Gerät ist bereits auf der Zielversion.")
            elif cmp > 0:
                add("version", "Versionsvergleich", "fail",
                    f"Installiert ist {info.installed_version}, neuer als {package.version} – kein Downgrade.")
            else:
                add("version", "Versionsvergleich", "ok", f"{info.installed_version} → {package.version}")

        # 6. Anlagenstopp
        if adapter.requires_stop_run:
            if package.stop_run_tested:
                add("stop_run", "STOP/RUN", "warn", "Update erfordert STOP/RUN – gesonderte Freigabe nötig.")
            else:
                add("stop_run", "STOP/RUN", "fail", "STOP/RUN ist für dieses Paket nicht als getestet freigegeben.")

    _finish(item)
    return item


def _finish(item: PlanItem) -> None:
    item.blockers = [c.message for c in item.checks if c.status == "fail"]
    item.warnings = [c.message for c in item.checks if c.status == "warn"]
    if item.status == "no_driver":
        return
    if item.blockers:
        item.status = "blocked"
    elif compare_versions(item.installed_version, item.target_version) == 0:
        item.status = "up_to_date"
    else:
        item.status = "ready"


def build_plan(
    devices: list[tuple[DeviceNode, tuple[str, ...]]],
    inventory: dict[str, DeviceInfo],
    adapters: dict[str, AdapterCapabilities],
    packages: list[FirmwarePackage],
    *,
    simulated: bool,
) -> list[PlanItem]:
    items = [
        plan_item(node, path, inventory.get(node.id), adapters.get(node.device_type or ""), packages, simulated=simulated)
        for node, path in devices
    ]
    items.sort(key=lambda i: (i.order_key, [p.casefold() for p in i.path], i.title.casefold(), i.entry_id))
    for position, item in enumerate(items, start=1):
        item.position = position
    return items
