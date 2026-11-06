# Copyright (c) 2026 ads-tec Industrial IT GmbH, Germany
# Licensed under the BSD 2-Clause License. See LICENSE file for details.

import sys
import getpass
from pathlib import Path
from urllib.parse import urlparse

from pykeepass import PyKeePass
from pykeepass.exceptions import CredentialsError

import jsonrpcdevice

PROJEKT_ORDNER = Path(__file__).resolve().parent
KEEPASS_DATEI = PROJEKT_ORDNER / "Keypass" / "adstec_hackathon.kdbx"
FIRMWARE_ORDNER = PROJEKT_ORDNER / "Firmware"
KEEPASS_ORDNER = "Adstec"
KEEPASS_EINTRAG = "Adstec"


def host_aus_url(base_url):
    # jsonrpcdevice erwartet nur Host[:Port], ohne https:// und Pfad.
    return urlparse(base_url if "://" in base_url else f"https://{base_url}").netloc


def zugang_aus_keepass():
    master_passwort = getpass.getpass("KeePass Master-Passwort: ")
    kp = PyKeePass(KEEPASS_DATEI, password=master_passwort)

    ordner = kp.find_groups(name=KEEPASS_ORDNER, first=True)
    if ordner is None:
        raise RuntimeError(f"Ordner '{KEEPASS_ORDNER}' nicht in der KeePass-Datei gefunden.")
    eintrag = kp.find_entries(title=KEEPASS_EINTRAG, group=ordner, recursive=False, first=True)
    if eintrag is None:
        raise RuntimeError(f"Eintrag '{KEEPASS_EINTRAG}' nicht im Ordner '{KEEPASS_ORDNER}' gefunden.")

    base_url = eintrag.get_custom_property("base_url") or eintrag.url
    if not (base_url and eintrag.username and eintrag.password):
        raise RuntimeError("Im KeePass-Eintrag fehlen base_url, Benutzername oder Passwort.")
    return host_aus_url(base_url), eintrag.username, eintrag.password


def firmware_datei():
    dateien = sorted(FIRMWARE_ORDNER.glob("*.bin"))
    if len(dateien) != 1:
        raise RuntimeError(f"Im Ordner '{FIRMWARE_ORDNER.name}' muss genau eine .bin-Datei liegen (gefunden: {len(dateien)}).")
    return dateien[0]


def update_device(base_url, username, password, datei):
    """Einstiegspunkt für die Weboberfläche: lädt die Firmware hoch, danach startet die Firewall neu."""
    dev = jsonrpcdevice.AdstecJSONRPCDevice(host_aus_url(base_url), username, password)
    vorher = dev.status("imageversion")
    upload_result = dev.upload_file("firmware", str(datei))
    if upload_result is None:
        raise RuntimeError("Upload der Firmware fehlgeschlagen.")
    return {
        "previous_version": vorher,
        "upload_result": upload_result,
        "message": "Firmware hochgeladen, die Firewall startet neu.",
    }


if __name__ == "__main__":
    try:
        host, username, password = zugang_aus_keepass()
        firmware_path = firmware_datei()
    except FileNotFoundError:
        sys.exit(f"Fehler: KeePass-Datei nicht gefunden: {KEEPASS_DATEI}")
    except CredentialsError:
        sys.exit("Fehler: KeePass Master-Passwort falsch.")
    except RuntimeError as error:
        sys.exit(f"Fehler: {error}")
    print(f"Ziel-Firewall: https://{host}")
    print(f"Firmware-Datei: {firmware_path.name}")

    ergebnis = update_device(host, username, password, firmware_path)
    print(f"initial_firmware_version: {ergebnis['previous_version']}")
    print(f"upload_result: {ergebnis['upload_result']}")

    dev = jsonrpcdevice.wait_for_reboot(host, username, password, check_interval=3)

    current_firmware_version = dev.status("imageversion")

    print(f"Device rebooted with firmware: {current_firmware_version}")