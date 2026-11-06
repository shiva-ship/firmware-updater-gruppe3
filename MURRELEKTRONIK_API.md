# Murrelektronik IMPACT67: API und Integration

Gerät: IMPACT67 Pro PN DIO8 IOL8 M12L 5P, Artikel 54630.
Zugang: nur HTTP auf Port 80. Basic Auth geht dadurch unverschlüsselt über das Netz.

## API-Calls

Basis-URL: `http://<IP>`

| Schritt | Aufruf | Auth | Zweck |
|---|---|---|---|
| 1 | `GET /iolink/v1/gateway/identification` | keine | Identität, Firmware und Hardware lesen |
| 2 | `GET /netx/login` | Basic | Zugangsdaten einmal prüfen |
| 3 | `POST /netx/firmware` | Basic | Firmware hochladen |
| 4 | `POST /netx/reset` | Basic | Gerät neu starten, Firmware wird aktiv |
| 5 | `GET /iolink/v1/gateway/identification` | keine | Pollen, bis Zielversion gemeldet wird |

`/iolink/v1/...` ist die IO-Link-REST-API des Geräts. `/netx/...` stammt aus der Weboberfläche des Geräts und ist nicht öffentlich dokumentiert. Der Ablauf wurde am 05.11.2026 am echten Gerät bestätigt.

### Antwort von `identification`

```json
{
  "macAddress": "...",
  "serialNumber": "...",
  "productId": "298",
  "vendorName": "...",
  "productName": "...",
  "hardwareRevision": "V2.0.0",
  "firmwareRevision": "V1.9.1"
}
```

### Upload

- Header: `Content-Type: application/zip`
- Body: die Datei `FWUPDATE.ZIP` aus dem `.m3z`-Container, nicht die `.m3z`-Datei selbst.
- Pfad im Container: `Binaries/<vendorId>_<deviceId>_<articleNo>_<hwVersion>/FWUPDATE.ZIP`
- Timeout als ein Wert setzen, nicht als `(connect, read)`. Mit Tupel begrenzt `requests` das Senden auf den Connect-Wert, der Upload brach dadurch nach 10 s ab.
- Upload und Reset nie automatisch wiederholen. Nach einem Fehler ist der Gerätezustand unbekannt.

### Dauer beim Update V1.8.1 auf V1.9.1

| Phase | Zeit |
|---|---|
| Prüfung und Stabilitätscheck | 8 s |
| Upload | 76 s |
| Reset | 1 s |
| Flashen und Neustart | 132 s |
| Gesamt | 216 s |

## Firmware-Paket

`.m3z` ist ein ZIP mit `info.json` und der Firmware. `read_package()` prüft Dateiendung, Artikelnummer, Größe und CRC32. Liegt die `.md5`-Datei des Herstellers daneben, prüft der Treiber auch deren Inhalt. Diese Datei enthält einen SHA256-Wert.

Vor dem Upload prüft der Treiber außerdem Produkt-ID, Hardware-Hauptversion und Downgrade. Danach muss das Gerät fünfmal in Folge antworten.

## Treiber

```python
from murrelektronik import Impact67Driver

driver = Impact67Driver(base_url, username, password, progress=callback)
driver.get_info()
driver.update("Firmware/54630_1.09.01-V-00.m3z")
```

Der Treiber liest KeePass nicht selbst. URL, Benutzer und Passwort kommen vom Aufrufer, in der App aus `DeviceAccess`.

`update()` gibt immer ein Dict zurück:

| `status` | `phase` | Bedeutung |
|---|---|---|
| `ok` | | Zielversion vom Gerät bestätigt |
| `already_up_to_date` | | Nichts zu tun |
| `rejected` | `precheck` | Abgelehnt, Gerät unverändert |
| `network_failed` | `precheck` | Gerät unverändert |
| `network_failed` | `upload`, `wait_ready` | Zustand unbekannt, Lauf stoppen |
| `failed` | `upload`, `verify` | Zustand unbekannt, Lauf stoppen |

## Einbau in `firmware-management`

Neue Dateien:

- `murrelektronik.py` im Projektordner
- `backend/services/devices/murrelektronik.py`
- `tests/fake_impact67.py`, `tests/test_murrelektronik.py`, `tests/test_murrelektronik_adapter.py`

Hersteller `murrelektronik` zusätzlich eintragen:

| Datei | Stelle |
|---|---|
| `backend/services/keepass/tree.py` | `DeviceType`, `_VENDOR_KEYWORDS` |
| `backend/services/devices/base.py` | `Vendor`, `VENDOR_LABELS` |
| `backend/services/devices/__init__.py` | Import, `default_adapters`, `__all__` |
| `backend/services/firmware/__init__.py` | `FIRMWARE_SUFFIXES` um `".m3z": "murrelektronik"` |
| `backend/services/updates/planner.py` | `VENDOR_PRIORITY`, `EFFECTS`, Reihenfolge-Text |
| `backend/api/schemas.py` | `DeviceTypeLiteral`, `FirmwareFileOut.device_type` |
| `backend/services/devices/demo.py` | `_VERSIONS`, `_MODELS` |
| `frontend/src/api/types.ts` | `DeviceType` |
| `frontend/src/lib/labels.ts` | Bezeichnungen |
| `frontend/src/lib/selection.ts` | Zähler je Hersteller |
| `frontend/src/components/TreeView.tsx` | `DEVICE_ICON` |
| `frontend/src/pages/WorkspacePage.tsx` | Zähler je Hersteller |
| `.gitignore` | `Firmware/*.m3z`, `Firmware/*.md5` |
| `README.md` | Treiber-Tabelle, Firmware-Endungen |

## KeePass-Eintrag

- Titel oder Gruppe enthält `Murrelektronik`.
- URL: `http://<IP>`
- Benutzername und Passwort des Geräts
- Feld `SerialNumber`, sonst blockiert der Updateplan.

## Offen

- STOP und RUN der Steuerung: Der Adapter steht auf `requires_stop_run = False`. Mit `True` blockiert der Plan aktuell jedes Paket als nicht getestet.
- Der Reset dürfte die PROFINET-Verbindung zur laufenden Steuerung trennen. Nicht geprüft.
- Nicht geprüft: Lauf aus dem Container auf der IRF, Downgrade am Gerät, Abbruch mitten im Upload, Erhalt der Konfiguration nach dem Update.
