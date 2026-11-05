"""Erzeugt aus einer geöffneten KeePass-Datenbank eine reine Metadaten-Baumstruktur.

Es werden ausschließlich Gruppennamen, Eintragstitel, UUIDs und Seriennummern übernommen –
keine Passwörter, Benutzernamen, URLs oder Notizen. Notizen werden nur serverseitig nach
einer ausdrücklich gekennzeichneten Seriennummer durchsucht; ihr Inhalt verlässt den Server nicht.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

SERIAL_FIELD_NAMES: tuple[str, ...] = ("SerialNumber", "Serialnummer", "serial_number")
MAX_DEPTH = 256
UNNAMED_GROUP = "Unbenannte Gruppe"
UNNAMED_ENTRY = "Unbenannter Eintrag"

SerialSource = Literal["field", "notes"]

# Nur ausdrücklich beschriftete Seriennummern werden erkannt, z. B.
#   "Serial: AX20237856", "SerialNumber = AX…", "Seriennummer: …", "S/N: …", "SN# …"
# Das Label darf nicht Teil eines längeren Wortes sein; der Wert ist ein einzelnes Token.
_NOTES_SERIAL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:serial[\s_-]?(?:number|no\.?|nr\.?)|serial|seriennummer|seriennr\.?|serialnummer|s/n|sn)"
    r"\s*[:=#]\s*"
    r"(?P<value>[A-Za-z0-9][A-Za-z0-9._/-]{2,63})",
    re.IGNORECASE,
)
_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


@dataclass(frozen=True)
class DeviceNode:
    id: str
    title: str
    serial_number: str | None
    serial_source: SerialSource | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "serial_number": self.serial_number,
            "serial_source": self.serial_source,
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


def extract_serial(custom_fields: Mapping[str, Any]) -> str | None:
    """Liest die Seriennummer aus bekannten Custom-Fields (Priorität in Reihenfolge von
    ``SERIAL_FIELD_NAMES``; exakte Schreibweise vor Groß-/Kleinschreibungs-Varianten).
    Es wird nichts abgeleitet oder erfunden."""
    for name in SERIAL_FIELD_NAMES:
        if name in custom_fields:
            value = _clean(custom_fields[name])
            if value:
                return value
    folded = {k.casefold(): v for k, v in custom_fields.items() if isinstance(k, str)}
    for name in SERIAL_FIELD_NAMES:
        value = _clean(folded.get(name.casefold()))
        if value:
            return value
    return None


def extract_serial_from_notes(notes: str | None) -> str | None:
    """Sucht in den Notizen nach einer beschrifteten Seriennummer (erste Fundstelle).
    IP-Adressen werden nie als Seriennummer übernommen."""
    if not notes:
        return None
    for match in _NOTES_SERIAL_PATTERN.finditer(notes):
        value = match.group("value").rstrip("./-")
        if len(value) >= 3 and not _IPV4.match(value):
            return value
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


def _clean_label(value: Any, fallback: str) -> str:
    return _clean(value) or fallback


def build_tree(kp: Any) -> GroupNode:
    """Baut den Baum aus einem ``pykeepass.PyKeePass``-Objekt. Der Papierkorb wird ausgelassen."""
    recycle_bin = getattr(kp, "recyclebin_group", None)
    recycle_uuid = getattr(recycle_bin, "uuid", None) if recycle_bin is not None else None

    def convert(group: Any, depth: int) -> GroupNode:
        node = GroupNode(id=str(group.uuid), name=_clean_label(group.name, UNNAMED_GROUP))
        for entry in group.entries:
            serial, source = resolve_serial(entry.custom_properties or {}, entry.notes)
            node.entries.append(
                DeviceNode(
                    id=str(entry.uuid),
                    title=_clean_label(entry.title, UNNAMED_ENTRY),
                    serial_number=serial,
                    serial_source=source,
                )
            )
        if depth < MAX_DEPTH:
            for sub in group.subgroups:
                if recycle_uuid is not None and sub.uuid == recycle_uuid:
                    continue
                node.groups.append(convert(sub, depth + 1))
        return node

    return convert(kp.root_group, 0)


def tree_stats(root: GroupNode) -> dict[str, int]:
    groups = list(root.iter_groups())
    entries = [e for g in groups for e in g.entries]
    return {
        "groups": len(groups) - 1,  # ohne Wurzelgruppe
        "entries": len(entries),
        "entries_without_serial": sum(1 for e in entries if e.serial_number is None),
        "serials_from_notes": sum(1 for e in entries if e.serial_source == "notes"),
    }
