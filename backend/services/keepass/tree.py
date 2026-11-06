"""Erzeugt aus einer geöffneten KeePass-Datenbank eine reine Metadaten-Baumstruktur.

Übernommen werden Gruppennamen, Eintragstitel, UUIDs, Seriennummern, der erkannte Hersteller
sowie nicht geheime Geräteangaben (Host/IP aus der URL, MAC, Modell, Update-Reihenfolge).
Passwörter und Benutzernamen werden nie übernommen. Notizen werden serverseitig nach der
Seriennummer durchsucht und nur in geschwärzter Form (Passwort-/PIN-Zeilen ausgeblendet) für
die Detailansicht vorgehalten – nicht im Baum selbst.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal
from urllib.parse import urlsplit

SERIAL_FIELD_NAMES: tuple[str, ...] = ("SerialNumber", "Serialnummer", "Seriennummer", "serial_number", "Serial")
MAC_FIELD_NAMES: tuple[str, ...] = ("MAC", "MAC-Adresse", "MacAddress", "mac_address", "mac")
MODEL_FIELD_NAMES: tuple[str, ...] = ("Model", "Modell", "model")
ORDER_FIELD_NAMES: tuple[str, ...] = ("UpdateOrder", "update_order", "Updatereihenfolge")
MAX_DEPTH = 256
MAX_NOTES_LENGTH = 4000
UNNAMED_GROUP = "Unbenannte Gruppe"
UNNAMED_ENTRY = "Unbenannter Eintrag"

SerialSource = Literal["field", "notes"]
SerialStatus = Literal["ok", "missing", "duplicate"]
DeviceType = Literal["balluff", "adstec", "siemens"]

# Beschriftete Seriennummern, z. B.
#   "Serial: AX20237856", "SerialNumber = AX…", "Seriennummer: …", "S/N: …", "SN# …"
# Das Label darf nicht Teil eines längeren Wortes sein; der Wert ist ein einzelnes Token.
_NOTES_SERIAL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:serial[\s_-]?(?:number|no\.?|nr\.?)|serial|seriennummer|seriennr\.?|serialnummer|s/n|sn)"
    r"\s*[:=#]\s*"
    # Siemens-Seriennummern enthalten ein Leerzeichen: "S C-K2N123456"
    r"(?P<value>(?:S\s?C-)?[A-Za-z0-9][A-Za-z0-9._/-]{2,63})",
    re.IGNORECASE,
)
# Notizen, die ausschließlich aus einem Wert bestehen, z. B. "AX20339256".
_BARE_SERIAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{3,63}$")
_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_MAC = re.compile(r"(?<![0-9A-Fa-f:-])((?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2})(?![0-9A-Fa-f:-])")
# Zeilen mit Geheimnissen werden vor der Anzeige geschwärzt.
_SECRET_LINE = re.compile(
    r"^(?P<label>\s*[^\n:=]{0,40}?(?:passwor[dt]|passwd|kennwort|pwd|pin|puk|secret|token|api[\s_-]?key|"
    r"private[\s_-]?key|schlüssel|psk|wpa)[^\n:=]{0,20}?\s*[:=])(?P<value>.*)$",
    re.IGNORECASE | re.MULTILINE,
)
REDACTED = " •••••• (ausgeblendet)"

# Hersteller anhand von Eintragstitel bzw. Gruppennamen (ohne Leer-, Binde- und Unterstriche).
_VENDOR_KEYWORDS: tuple[tuple[DeviceType, tuple[str, ...]], ...] = (
    ("balluff", ("balluff",)),
    ("adstec", ("adstec",)),
    ("siemens", ("siemens", "simatic", "s71200", "s71500", "s7300", "s7400")),
)


@dataclass(frozen=True)
class DeviceNode:
    id: str
    title: str
    serial_number: str | None
    serial_source: SerialSource | None = None
    device_type: DeviceType | None = None
    serial_status: SerialStatus = "missing"
    host: str | None = None
    mac_address: str | None = None
    model: str | None = None
    update_order: int | None = None
    has_notes: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "serial_number": self.serial_number,
            "serial_source": self.serial_source,
            "serial_status": self.serial_status,
            "device_type": self.device_type,
            "host": self.host,
            "mac_address": self.mac_address,
            "model": self.model,
            "update_order": self.update_order,
            "has_notes": self.has_notes,
        }


@dataclass
class GroupNode:
    id: str
    name: str
    entries: list[DeviceNode] = field(default_factory=list)
    groups: list[GroupNode] = field(default_factory=list)

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    @property
    def total_entry_count(self) -> int:
        return self.entry_count + sum(g.total_entry_count for g in self.groups)

    def iter_groups(self):
        yield self
        for g in self.groups:
            yield from g.iter_groups()

    def iter_entries_with_path(self, path: tuple[str, ...] = ()):
        for entry in self.entries:
            yield entry, path
        for g in self.groups:
            yield from g.iter_entries_with_path((*path, g.name))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "entry_count": self.entry_count,
            "total_entry_count": self.total_entry_count,
            "entries": [e.to_dict() for e in self.entries],
            "groups": [g.to_dict() for g in self.groups],
        }


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _field(custom_fields: Mapping[str, Any], names: Iterable[str]) -> str | None:
    """Exakte Schreibweise vor Groß-/Kleinschreibungs-Varianten, Priorität in Reihenfolge von ``names``."""
    names = tuple(names)
    for name in names:
        if name in custom_fields:
            value = _clean(custom_fields[name])
            if value:
                return value
    folded = {k.casefold(): v for k, v in custom_fields.items() if isinstance(k, str)}
    for name in names:
        value = _clean(folded.get(name.casefold()))
        if value:
            return value
    return None


def extract_serial(custom_fields: Mapping[str, Any]) -> str | None:
    """Liest die Seriennummer aus bekannten Custom-Fields. Es wird nichts abgeleitet oder erfunden."""
    return _field(custom_fields, SERIAL_FIELD_NAMES)


def _plausible_serial(value: str) -> bool:
    return len(value) >= 3 and not _IPV4.match(value) and not _MAC.fullmatch(value)


def extract_serial_from_notes(notes: str | None) -> str | None:
    """Erkennt die Seriennummer in den Notizen:

    1. beschriftet (``SerialNumber:``, ``Serial:``, ``Seriennummer:``, ``S/N:`` …) – erste Fundstelle
    2. als alleiniger Inhalt der Notiz, z. B. ``AX20339256`` (muss mindestens eine Ziffer enthalten)

    IP- und MAC-Adressen werden nie als Seriennummer übernommen.
    """
    if not notes:
        return None
    for match in _NOTES_SERIAL_PATTERN.finditer(notes):
        value = match.group("value").rstrip("./-")
        if _plausible_serial(value):
            return value
    bare = notes.strip()
    if _BARE_SERIAL.fullmatch(bare) and any(c.isdigit() for c in bare) and _plausible_serial(bare):
        return bare
    return None


def resolve_serial(custom_fields: Mapping[str, Any], notes: str | None) -> tuple[str | None, SerialSource | None]:
    """Custom-Field hat Vorrang vor den Notizen."""
    serial = extract_serial(custom_fields)
    if serial:
        return serial, "field"
    serial = extract_serial_from_notes(notes)
    if serial:
        return serial, "notes"
    return None, None


def extract_mac(custom_fields: Mapping[str, Any], notes: str | None) -> str | None:
    value = _field(custom_fields, MAC_FIELD_NAMES)
    if value and _MAC.fullmatch(value):
        return value.upper().replace("-", ":")
    match = _MAC.search(notes or "")
    return match.group(1).upper().replace("-", ":") if match else None


def extract_host(url: str | None) -> str | None:
    """Host bzw. IP-Adresse aus der Eintrags-URL (ohne Schema, Pfad und Zugangsdaten)."""
    url = _clean(url)
    if not url:
        return None
    try:
        parts = urlsplit(url if "://" in url else f"https://{url}")
        return parts.hostname or None
    except ValueError:
        return None


def extract_order(custom_fields: Mapping[str, Any]) -> int | None:
    value = _field(custom_fields, ORDER_FIELD_NAMES)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def redact_notes(notes: str | None) -> tuple[str | None, bool]:
    """Blendet Zeilen mit Passwörtern, PINs, Schlüsseln o. Ä. aus. Gibt (Text, geschwärzt?) zurück."""
    text = _clean(notes)
    if text is None:
        return None, False
    redacted, count = _SECRET_LINE.subn(lambda m: m.group("label") + REDACTED, text)
    return redacted[:MAX_NOTES_LENGTH], count > 0


def _clean_label(value: Any, fallback: str) -> str:
    return _clean(value) or fallback


def detect_device_type(names: Iterable[str | None]) -> DeviceType | None:
    """Erkennt den Hersteller am Namen. Reihenfolge: Eintragstitel, dann Gruppen nach außen
    (ohne Wurzelgruppe, deren Name oft dem Dateinamen entspricht)."""
    for name in names:
        folded = re.sub(r"[\s_-]", "", (name or "").casefold())
        for vendor, keywords in _VENDOR_KEYWORDS:
            if any(k in folded for k in keywords):
                return vendor
    return None


def _serial_key(serial: str) -> str:
    return serial.strip().casefold()


def mark_serial_status(root: GroupNode) -> None:
    """Setzt ``serial_status``: fehlende und mehrfach vergebene Seriennummern werden markiert,
    damit für sie keine automatische Gerätezuordnung erfolgt."""
    counts = Counter(_serial_key(e.serial_number) for g in root.iter_groups() for e in g.entries if e.serial_number)
    for group in root.iter_groups():
        group.entries = [
            replace(
                e,
                serial_status="missing"
                if not e.serial_number
                else ("duplicate" if counts[_serial_key(e.serial_number)] > 1 else "ok"),
            )
            for e in group.entries
        ]


# Beispieleinträge, die KeePass in neuen Datenbanken anlegt, verweisen auf keepass.info.
_SAMPLE_HOSTS = ("keepass.info",)


def is_device_entry(node: DeviceNode) -> bool:
    """Nur Einträge mit Gerätedaten (Adresse oder Seriennummer) werden angezeigt.
    KeePass-Beispieleinträge und leere Einträge werden ausgeblendet."""
    if node.host and any(node.host == h or node.host.endswith("." + h) for h in _SAMPLE_HOSTS):
        return False
    return bool(node.host or node.serial_number)


def build_tree(kp: Any, notes_out: dict[str, tuple[str, bool]] | None = None) -> GroupNode:
    """Baut den Baum aus einem ``pykeepass.PyKeePass``-Objekt. Der Papierkorb wird ausgelassen,
    ebenso Einträge ohne Gerätedaten und Gruppen, die danach (auch verschachtelt) leer sind.

    Ist ``notes_out`` angegeben, werden dort die geschwärzten Notizen je Eintrags-UUID abgelegt."""
    recycle_bin = getattr(kp, "recyclebin_group", None)
    recycle_uuid = getattr(recycle_bin, "uuid", None) if recycle_bin is not None else None

    def convert(group: Any, depth: int, path: tuple[str, ...]) -> GroupNode:
        node = GroupNode(id=str(group.uuid), name=_clean_label(group.name, UNNAMED_GROUP))
        for entry in group.entries:
            custom = entry.custom_properties or {}
            serial, source = resolve_serial(custom, entry.notes)
            entry_id = str(entry.uuid)
            notes, redacted = redact_notes(entry.notes)
            device = DeviceNode(
                id=entry_id,
                title=_clean_label(entry.title, UNNAMED_ENTRY),
                serial_number=serial,
                serial_source=source,
                device_type=detect_device_type([entry.title, *reversed(path)]),
                host=extract_host(custom.get("base_url") or entry.url),
                mac_address=extract_mac(custom, entry.notes),
                model=_field(custom, MODEL_FIELD_NAMES),
                update_order=extract_order(custom),
                has_notes=notes is not None,
            )
            if not is_device_entry(device):
                continue
            if notes_out is not None and notes:
                notes_out[entry_id] = (notes, redacted)
            node.entries.append(device)
        if depth < MAX_DEPTH:
            for sub in group.subgroups:
                if recycle_uuid is not None and sub.uuid == recycle_uuid:
                    continue
                child = convert(sub, depth + 1, (*path, sub.name or ""))
                if child.total_entry_count > 0:
                    node.groups.append(child)
        return node

    root = convert(kp.root_group, 0, ())
    mark_serial_status(root)
    return root


def find_device(root: GroupNode, entry_id: str) -> tuple[DeviceNode, tuple[str, ...]] | None:
    for entry, path in root.iter_entries_with_path():
        if entry.id == entry_id:
            return entry, path
    return None


def tree_stats(root: GroupNode) -> dict[str, int]:
    groups = list(root.iter_groups())
    entries = [e for g in groups for e in g.entries]
    return {
        "groups": len(groups) - 1,  # ohne Wurzelgruppe
        "entries": len(entries),
        "entries_without_serial": sum(1 for e in entries if e.serial_number is None),
        "serials_from_notes": sum(1 for e in entries if e.serial_source == "notes"),
        "duplicate_serials": sum(1 for e in entries if e.serial_status == "duplicate"),
    }
