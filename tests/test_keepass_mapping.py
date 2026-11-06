"""Seriennummern-Erkennung und KeePass-Mapping."""

from __future__ import annotations

import pytest

from backend.services.keepass import build_tree, extract_serial_from_notes, redact_notes, resolve_serial
from tests.conftest import TEST_MASTER_PASSWORD


@pytest.mark.parametrize(
    ("notes", "expected"),
    [
        ("AX20339256", "AX20339256"),
        ("  AX20339256  \n", "AX20339256"),
        ("SerialNumber: AX20339256", "AX20339256"),
        ("Serial: AX20339256", "AX20339256"),
        ("Seriennummer: AX20339256", "AX20339256"),
        ("seriennummer:AX20339256", "AX20339256"),
        ("Serial: S C-K2N123456", "S C-K2N123456"),  # Siemens-Format
        ("Standort Halle 3\nS/N: 192.168.0.1\nSerial: AX20339256", "AX20339256"),  # IP → nächste Fundstelle
        ("Bitte Firmware prüfen", None),  # kein Wert, keine Ziffer
        ("192.168.0.1", None),  # IP-Adresse
        ("00:11:22:33:44:55", None),  # MAC-Adresse
        ("AX20339256 Halle 3", None),  # kein alleiniger Wert, keine Beschriftung
        ("", None),
        (None, None),
    ],
)
def test_serial_from_notes(notes, expected):
    assert extract_serial_from_notes(notes) == expected


def test_custom_field_has_priority_over_notes():
    assert resolve_serial({"SerialNumber": "FIELD1"}, "Serial: NOTES1") == ("FIELD1", "field")
    assert resolve_serial({}, "Serial: NOTES1") == ("NOTES1", "notes")
    assert resolve_serial({}, None) == (None, None)


def test_notes_are_redacted():
    text, redacted = redact_notes("SerialNumber: BL1\nPasswort: geheim123\nWLAN-PSK = abc")
    assert redacted is True
    assert "geheim123" not in text and "abc" not in text
    assert "SerialNumber: BL1" in text


def test_tree_from_kdbx(kdbx_file):
    from pykeepass import PyKeePass

    kp = PyKeePass(str(kdbx_file), password=TEST_MASTER_PASSWORD)
    notes: dict = {}
    root = build_tree(kp, notes)
    entries = {e.title: (e, path) for e, path in root.iter_entries_with_path()}

    # Hierarchie aus den echten Gruppen
    assert [g.name for g in root.groups] == ["Standort Esslingen", "Standort Nürtingen"]
    assert entries["Firewall Halle 1"][1] == ("Standort Esslingen", "Adstec")

    fw = entries["Firewall Halle 1"][0]
    assert fw.serial_number == "AX20339256" and fw.serial_source == "notes" and fw.serial_status == "ok"
    assert fw.device_type == "adstec" and fw.host == "192.168.0.1"
    # UUID ist die Zuordnungs-ID
    assert fw.id == str(kp.find_entries(title="Firewall Halle 1", first=True).uuid)

    assert entries["Master Linie 1"][0].device_type == "balluff"
    assert entries["SPS Presse"][0].device_type == "siemens"

    # Doppelte und fehlende Seriennummern werden markiert
    assert entries["Unbekanntes Gerät"][0].serial_status == "duplicate"
    assert entries["Zweites unbekanntes Gerät"][0].serial_status == "duplicate"
    assert entries["Ohne Seriennummer"][0].serial_status == "missing"

    # Leere Einträge, KeePass-Beispiele und leere Ordner werden nicht angezeigt
    assert "Leerer Eintrag" not in entries and "Sample Entry" not in entries
    assert all(g.total_entry_count > 0 for g in root.iter_groups())

    # Keine Geheimnisse im Baum
    serialized = str(root.to_dict())
    for secret in ("fw-secret", "bl-secret", "geheim123"):
        assert secret not in serialized
    # Notizen liegen getrennt und geschwärzt vor
    master_notes, redacted = notes[entries["Master Linie 1"][0].id]
    assert redacted and "geheim123" not in master_notes
