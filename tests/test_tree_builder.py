"""Unit-Tests der Baumerzeugung ohne HTTP-Schicht."""

from __future__ import annotations

from pykeepass import PyKeePass, create_database

from backend.services.keepass import build_tree, extract_serial, extract_serial_from_notes, resolve_serial, tree_stats
from backend.services.keepass.tree import UNNAMED_ENTRY

from .conftest import MASTER_PASSWORD


def test_extract_serial_priority_and_fallbacks():
    assert extract_serial({"SerialNumber": "A", "Serialnummer": "B", "serial_number": "C"}) == "A"
    assert extract_serial({"Serialnummer": "B", "serial_number": "C"}) == "B"
    assert extract_serial({"serial_number": "C"}) == "C"
    assert extract_serial({"SERIALNUMBER": " D "}) == "D"
    assert extract_serial({"SerialNumber": "", "serial_number": "E"}) == "E"


def test_extract_serial_never_invents_values():
    assert extract_serial({}) is None
    assert extract_serial({"IP": "192.168.1.10", "MAC": "00:11:22:33:44:55"}) is None
    assert extract_serial({"SerialNumber": "   "}) is None
    assert extract_serial({"SerialNumber": None}) is None


def test_serial_from_notes_labels():
    assert extract_serial_from_notes("Serial: AX20237856") == "AX20237856"
    assert extract_serial_from_notes("Gerät im Schrank 3\nSeriennummer: AX-2023/7856\n") == "AX-2023/7856"
    assert extract_serial_from_notes("S/N: BX55667788") == "BX55667788"
    assert extract_serial_from_notes("SN#  12345678") == "12345678"
    assert extract_serial_from_notes("serial_number = ax1") == "ax1"
    assert extract_serial_from_notes("serial_number = a1") is None  # zu kurz → kein Treffer
    assert extract_serial_from_notes("SerialNumber=QQ998877, IP: 10.0.0.1") == "QQ998877"
    assert extract_serial_from_notes("IRF3401 Serial No.: AX111222 Firmware 2.1") == "AX111222"


def test_serial_from_notes_never_guesses():
    assert extract_serial_from_notes(None) is None
    assert extract_serial_from_notes("") is None
    assert extract_serial_from_notes("IP: 192.168.0.10\nMAC: 00:11:22:33:44:55") is None
    assert extract_serial_from_notes("AX20237856") is None  # ohne Beschriftung nicht übernehmen
    assert extract_serial_from_notes("Serial: 192.168.0.10") is None
    assert extract_serial_from_notes("Busn: ABC12345") is None  # "sn" nur als Wortende → kein Label
    assert extract_serial_from_notes("Personal: Max") is None


def test_field_has_priority_over_notes():
    assert resolve_serial({"SerialNumber": "FIELD123"}, "Serial: NOTES456") == ("FIELD123", "field")
    assert resolve_serial({}, "Serial: NOTES456") == ("NOTES456", "notes")
    assert resolve_serial({"SerialNumber": " "}, "Serial: NOTES456") == ("NOTES456", "notes")
    assert resolve_serial({}, "nichts") == (None, None)


def test_deeply_nested_and_untitled(tmp_path):
    path = tmp_path / "deep.kdbx"
    kp = create_database(str(path), password=MASTER_PASSWORD)
    parent = kp.root_group
    for level in range(12):
        parent = kp.add_group(parent, f"Ebene {level}")
    entry = kp.add_entry(parent, "Gerät", "u", "p")
    entry.title = ""
    kp.save()

    root = build_tree(PyKeePass(str(path), password=MASTER_PASSWORD))
    node = root
    for level in range(12):
        assert len(node.groups) == 1
        node = node.groups[0]
        assert node.name == f"Ebene {level}"
    assert node.entries[0].title == UNNAMED_ENTRY
    assert node.entries[0].serial_number is None
    assert root.total_entry_count == 1
    assert tree_stats(root) == {"groups": 12, "entries": 1, "entries_without_serial": 1, "serials_from_notes": 0}


def test_empty_database(tmp_path):
    path = tmp_path / "empty.kdbx"
    create_database(str(path), password=MASTER_PASSWORD).save()
    root = build_tree(PyKeePass(str(path), password=MASTER_PASSWORD))
    assert root.groups == [] and root.entries == []
    assert root.to_dict()["total_entry_count"] == 0
