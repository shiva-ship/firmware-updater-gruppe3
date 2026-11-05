"""Erzeugt eine Demo-KeePass-Datenbank zum Ausprobieren (enthält nur Fantasiedaten).

    .\.venv\Scripts\python.exe scripts\make-demo-kdbx.py C:\Temp\demo.kdbx

Das Masterpasswort wird verdeckt abgefragt. Die Datei NICHT ins Repository legen.
"""

from __future__ import annotations

import getpass
import secrets
import sys
from pathlib import Path

from pykeepass import create_database

DEVICES = {
    "ADS-TEC": [("IRF3401", "AX20237856"), ("IRF3801", "AX20229229")],
    "Balluff": [("BNI XG3", None)],
    "Weidmüller": [("UC20-M3000", None)],
    "Murrelektronik": [],
    "Siemens": [],
}


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    target = Path(sys.argv[1])
    if target.exists():
        print(f"Abbruch: {target} existiert bereits.")
        return 1
    password = getpass.getpass("Masterpasswort für die Demo-Datenbank: ")
    if not password or password != getpass.getpass("Wiederholen: "):
        print("Abbruch: Passwörter leer oder ungleich.")
        return 1

    kp = create_database(str(target), password=password)
    for group_name, devices in DEVICES.items():
        group = kp.add_group(kp.root_group, group_name)
        for title, serial in devices:
            entry = kp.add_entry(group, title, "admin", secrets.token_urlsafe(16))
            if serial:
                entry.set_custom_property("SerialNumber", serial)
    werk = kp.add_group(kp.find_groups(name="ADS-TEC", first=True), "Werk A")
    halle = kp.add_group(werk, "Halle 2")
    entry = kp.add_entry(halle, "IRF2000", "service", secrets.token_urlsafe(16))
    entry.set_custom_property("Serialnummer", "AX19870042")
    kp.save()
    print(f"Demo-Datenbank erstellt: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
