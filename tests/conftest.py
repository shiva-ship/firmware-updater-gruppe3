"""Gemeinsame Test-Fixtures. Es werden nur selbst erzeugte Test-KDBX-Dateien verwendet."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_MASTER_PASSWORD = "Test-Master-Passwort-1!"  # nur für die erzeugte Test-Datenbank


@pytest.fixture
def kdbx_file(tmp_path: Path) -> Path:
    """KDBX mit Standorten, Herstellern, Seriennummern in verschiedenen Schreibweisen und einem Duplikat."""
    from pykeepass import create_database

    path = tmp_path / "test.kdbx"
    kp = create_database(str(path), password=TEST_MASTER_PASSWORD)
    halle1 = kp.add_group(kp.root_group, "Standort Esslingen")
    adstec = kp.add_group(halle1, "Adstec")
    balluff = kp.add_group(halle1, "Balluff")
    halle2 = kp.add_group(kp.root_group, "Standort Nürtingen")
    siemens = kp.add_group(halle2, "Siemens")

    e = kp.add_entry(adstec, "Firewall Halle 1", "admin", "fw-secret", url="https://192.168.0.1")
    e.notes = "AX20339256"
    e = kp.add_entry(balluff, "Master Linie 1", "admin", "bl-secret", url="192.168.0.10")
    e.notes = "SerialNumber: BL1000001\nPasswort: geheim123"
    e = kp.add_entry(balluff, "Master Linie 2", "admin", "bl-secret2", url="192.168.0.11")
    e.notes = "Seriennummer: BL1000002"
    e = kp.add_entry(siemens, "SPS Presse", "", "", url="192.168.0.200")
    e.notes = "Serial: S7X0001"
    e = kp.add_entry(halle2, "Unbekanntes Gerät", "u", "p", url="10.0.0.5")
    e.notes = "Serial: DUP-0001"
    e = kp.add_entry(halle2, "Zweites unbekanntes Gerät", "u", "p", url="10.0.0.6")
    e.notes = "Serial: DUP-0001"
    kp.add_entry(halle2, "Ohne Seriennummer", "u", "p", url="10.0.0.7")
    # Soll ausgeblendet werden: leerer Eintrag, KeePass-Beispiel, leere (verschachtelte) Ordner
    kp.add_entry(halle2, "Leerer Eintrag", "u", "p")
    kp.add_entry(kp.root_group, "Sample Entry", "User Name", "Password", url="https://keepass.info/")
    kp.add_group(kp.add_group(kp.root_group, "General"), "Leer")
    kp.add_group(kp.root_group, "Windows")
    kp.save()
    return path


@pytest.fixture
def firmware_dir(tmp_path: Path) -> Path:
    d = tmp_path / "Firmware"
    d.mkdir()
    (d / "Ads-tec-IRF3xxx-2.3.4-SVN-R1.B-1.bin").write_bytes(b"ADSTEC-FIRMWARE-TEST" * 100)
    (d / "bni-test.bff").write_bytes(b"BALLUFF-FIRMWARE-TEST" * 100)
    return d
