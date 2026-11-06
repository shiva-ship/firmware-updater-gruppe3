import getpass
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import requests
import urllib3
from pykeepass import PyKeePass
from pykeepass.exceptions import CredentialsError

PROJEKT_ORDNER = Path(__file__).resolve().parent
KEEPASS_DATEI = PROJEKT_ORDNER / "Keypass" / "adstec_hackathon.kdbx"
FIRMWARE_ORDNER = PROJEKT_ORDNER / "Firmware"
KEEPASS_ORDNER = "Balluff"
KEEPASS_EINTRAG = "Balluff"
TIMEOUT = 10
UPDATE_TIMEOUT = 600

HTTP_FEHLER = {
    400: "Ungültige Anfrage",
    401: "Nicht angemeldet oder Benutzername/Passwort falsch",
    403: "Keine Berechtigung für diese Aktion",
    404: "Endpunkt nicht gefunden",
    500: "Interner Fehler auf dem Master",
    503: "Master ist gerade nicht verfügbar",
}

# Master nutzt ein selbstsigniertes Zertifikat.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class Zugang:
    base_url: str
    username: str
    password: str = field(repr=False)


def normalisiere_url(base_url: str) -> str:
    if "://" not in base_url:
        base_url = f"https://{base_url}"
    return base_url.rstrip("/")


def zugang_aus_keepass() -> Zugang:
    master_passwort = getpass.getpass("KeePass Master-Passwort: ")
    kp = PyKeePass(KEEPASS_DATEI, password=master_passwort)

    ordner = kp.find_groups(name=KEEPASS_ORDNER, first=True)
    if ordner is None:
        raise RuntimeError(f"Ordner '{KEEPASS_ORDNER}' nicht in der KeePass-Datei gefunden.")
    eintrag = kp.find_entries(title=KEEPASS_EINTRAG, group=ordner, recursive=False, first=True)
    if eintrag is None:
        raise RuntimeError(f"Eintrag '{KEEPASS_EINTRAG}' nicht im Ordner '{KEEPASS_ORDNER}' gefunden.")

    # base_url kann als eigenes Feld oder im URL-Feld des Eintrags stehen.
    base_url = eintrag.get_custom_property("base_url") or eintrag.url
    if not (base_url and eintrag.username and eintrag.password):
        raise RuntimeError("Im KeePass-Eintrag fehlen base_url, Benutzername oder Passwort.")
    return Zugang(normalisiere_url(base_url), eintrag.username, eintrag.password)


def login(session: requests.Session, zugang: Zugang) -> None:
    response = session.post(
        f"{zugang.base_url}/users/login",
        json={"username": zugang.username, "password": zugang.password},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    token = response.json().get("Bearer")
    if not token:
        raise RuntimeError("Die Login-Antwort enthält kein Bearer-Token.")
    session.headers["Authorization"] = f"Bearer {token}"


def firmware_datei() -> Path:
    dateien = sorted(FIRMWARE_ORDNER.glob("*.bff"))
    if len(dateien) != 1:
        raise RuntimeError(f"Im Ordner '{FIRMWARE_ORDNER.name}' muss genau eine .bff-Datei liegen (gefunden: {len(dateien)}).")
    return dateien[0]


def firmware_id_ermitteln(session: requests.Session, base_url: str) -> str:
    response = session.get(f"{base_url}/firmwares", timeout=TIMEOUT)
    response.raise_for_status()
    firmwares = response.json().get("firmwares", [])
    if not firmwares:
        raise RuntimeError("Der Master meldet keine Firmware-Komponenten.")
    if len(firmwares) > 1:
        ids = ", ".join(fw["firmwareId"] for fw in firmwares)
        raise RuntimeError(f"Der Master meldet mehrere Firmware-Komponenten ({ids}). Automatische Auswahl nicht möglich.")
    return firmwares[0]["firmwareId"]


def firmware_update(session: requests.Session, zugang: Zugang, datei: Path) -> dict:
    base_url = zugang.base_url
    firmware_id = firmware_id_ermitteln(session, base_url)
    fw_url = f"{base_url}/firmwares/{firmware_id}"

    response = session.get(fw_url, timeout=TIMEOUT)
    response.raise_for_status()
    vorher = response.json().get("version")

    with datei.open("rb") as f:
        response = session.post(
            f"{fw_url}/upload",
            files={"file": (datei.name, f, "application/octet-stream")},
            timeout=UPDATE_TIMEOUT,
        )
    response.raise_for_status()
    upload = response.json() if response.content else {}

    response = session.post(f"{fw_url}/install", timeout=UPDATE_TIMEOUT)
    response.raise_for_status()
    install = response.json() if response.content else {}

    neustart = bool(upload.get("rebootNecessary") or install.get("rebootNecessary"))
    if neustart:
        try:
            session.post(f"{fw_url}/reboot", timeout=TIMEOUT)
        except requests.ConnectionError:
            pass  # Der Master trennt die Verbindung beim Neustart teils sofort.

    return {
        "firmware_id": firmware_id,
        "previous_version": vorher,
        "expected": install,
        "message": "Firmware installiert, der Master startet neu." if neustart else "Firmware installiert.",
    }


def update_device(base_url: str, username: str, password: str, datei: Path) -> dict:
    """Einstiegspunkt für die Weboberfläche. Fehler kommen als RuntimeError mit lesbarem Text."""
    zugang = Zugang(normalisiere_url(base_url), username, password)
    with requests.Session() as session:
        session.verify = False
        try:
            login(session, zugang)
            return firmware_update(session, zugang, datei)
        except requests.HTTPError as error:
            status = error.response.status_code
            text = HTTP_FEHLER.get(status, "Unerwartete Antwort vom Master")
            raise RuntimeError(f"{text} (HTTP {status})") from None
        except requests.ConnectionError:
            raise RuntimeError(f"Master unter {zugang.base_url} nicht erreichbar.") from None
        except requests.Timeout:
            raise RuntimeError("Der Master hat nicht rechtzeitig geantwortet.") from None
        except ValueError:
            raise RuntimeError("Antwort des Masters ist kein gültiges JSON.") from None


def main() -> int:
    try:
        zugang = zugang_aus_keepass()
        datei = firmware_datei()
    except FileNotFoundError:
        print(f"Fehler: KeePass-Datei nicht gefunden: {KEEPASS_DATEI}")
        return 1
    except CredentialsError:
        print("Fehler: KeePass Master-Passwort falsch.")
        return 1
    except RuntimeError as error:
        print(f"Fehler: {error}")
        return 1

    base_url = zugang.base_url
    with requests.Session() as session:
        session.verify = False
        try:
            login(session, zugang)
            print("Login erfolgreich.")
            print(f"Firmware-Datei: {datei.name}. Update läuft ...")
            ergebnis = firmware_update(session, zugang, datei)
            print(f"Vorher installiert: {ergebnis['previous_version']}")
            print(f"Erwartete Firmware: {json.dumps(ergebnis['expected'], ensure_ascii=False)}")
            print(ergebnis["message"])

        except requests.HTTPError as error:
            status = error.response.status_code
            text = HTTP_FEHLER.get(status, "Unerwartete Antwort vom Master")
            print(f"Fehler: {text} (HTTP {status}, {error.request.url})")
        except requests.ConnectTimeout:
            print(f"Fehler: Zeitüberschreitung beim Verbinden mit {base_url}. Ist die IP-Adresse korrekt?")
        except requests.ConnectionError:
            print(f"Fehler: Master unter {base_url} nicht erreichbar. Netzwerkkabel und IP-Adresse prüfen.")
        except requests.Timeout:
            print(f"Fehler: Master hat nicht innerhalb von {TIMEOUT} Sekunden geantwortet.")
        except ValueError:
            print("Fehler: Antwort des Masters ist kein gültiges JSON.")
        except RuntimeError as error:
            print(f"Fehler: {error}")
        else:
            return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
