import json
import sys

import requests
from pykeepass.exceptions import CredentialsError

from balluff_update import HTTP_FEHLER, KEEPASS_DATEI, TIMEOUT, login, zugang_aus_keepass


def main() -> int:
    try:
        zugang = zugang_aus_keepass()
    except FileNotFoundError:
        print(f"Fehler: KeePass-Datei nicht gefunden: {KEEPASS_DATEI}")
        return 1
    except CredentialsError:
        print("Fehler: KeePass Master-Passwort falsch.")
        return 1
    except RuntimeError as error:
        print(f"Fehler: {error}")
        return 1

    with requests.Session() as session:
        session.verify = False
        try:
            login(session, zugang)
            response = session.get(f"{zugang.base_url}/identification", timeout=TIMEOUT)
            response.raise_for_status()
            print(json.dumps(response.json(), indent=2, ensure_ascii=False))
            return 0

        except requests.HTTPError as error:
            status = error.response.status_code
            text = HTTP_FEHLER.get(status, "Unerwartete Antwort vom Master")
            print(f"Fehler: {text} (HTTP {status}, {error.request.url})")
        except requests.ConnectionError:
            print(f"Fehler: Master unter {zugang.base_url} nicht erreichbar.")
        except requests.Timeout:
            print(f"Fehler: Master hat nicht innerhalb von {TIMEOUT} Sekunden geantwortet.")
        except (ValueError, RuntimeError) as error:
            print(f"Fehler: {error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
