# ADS-TEC Firmware Management (Security Manager)

Lokale Webanwendung, mit der sich die Firmware von Industriegeräten aus einer KeePass-Datei heraus planen, prüfen und kontrolliert aktualisieren lässt.

## Start

| Modus | Befehl | Wirkung |
|---|---|---|
| LIVE (Standard) | `start.cmd` | Die Python-Gerätetreiber sprechen die Geräte im Industrienetz an. |
| DEMO | `start-demo.cmd` | Echte KeePass-Daten, **simulierte** Geräte. Es wird kein Gerät kontaktiert oder verändert. |

Der aktive Modus steht in der Kopfzeile (gelb: DEMO-MODUS, rot: LIVE-MODUS). Er lässt sich auch über `ASM_DEVICE_MODE=demo|live` oder `.env` setzen.

## Ablauf

1. Anmelden und die `.kdbx`-Datei hochladen.
2. **Daten aktualisieren**: Das Masterpasswort wird abgefragt, danach werden Gruppen, Geräte und Seriennummern ausgelesen.
3. Geräte im Baum auswählen: einzeln per Häkchen, ganze Standorte/Gruppen per Gruppen-Häkchen, alle Geräte eines Herstellers über **+ Hersteller auswählen**, alle über **Alle auswählen**, keine über **Auswahl aufheben**. Die Auswahl startet kein Update.
4. **Firmwareupdates vorbereiten**: Der Updateplan zeigt je Gerät Identität, Treiber, Verbindung, installierte Version, Paket, Integrität, Kompatibilität und Reihenfolge. Im LIVE-Modus werden die Geräte dafür nur lesend abgefragt (Masterpasswort erforderlich).
5. **Dry-Run ausführen** prüft den Ablauf ohne Geräteänderung.
6. **Update freigeben**: Masterpasswort erneut eingeben (wird nur serverseitig geprüft), dann ausdrücklich bestätigen und **Installation starten**.
7. Die Geräte werden nacheinander aktualisiert und anschließend verifiziert. Am Ende erscheint ein Ergebnisbericht (Download als JSON).

## Firmwarepakete freigeben

Dateien liegen im Ordner `Firmware` (`.bin` = ads-tec, `.bff` = Balluff). Ein Paket wird erst installiert, wenn es unter **Firmware & Treiber → Freigeben** mit Zielversion und kompatiblen Modellen freigegeben ist. Optional lässt sich die SHA-256-Prüfsumme des Herstellers hinterlegen. Die Freigabe steht in `Firmware/firmware-manifest.json`. Ändert sich die Datei danach, wird sie als „Prüfsumme abweichend“ blockiert.

## KeePass-Konventionen

- **Hersteller**: aus dem Eintragstitel oder dem Gruppennamen (`Balluff`, `Adstec`/`ads-tec`, `Siemens`/`SIMATIC`).
- **Seriennummer**: Feld `SerialNumber`/`Seriennummer` oder in den Notes, entweder als alleiniger Wert (`AX20339256`) oder beschriftet (`SerialNumber:`, `Serial:`, `Seriennummer:`, `S/N:`). Fehlende oder doppelte Seriennummern blockieren das Update.
- **Adresse**: URL-Feld oder eigenes Feld `base_url`. Benutzername und Passwort stehen im Eintrag.
- Optional: `Model`, `MAC`, `UpdateOrder` (Zahl, überschreibt die Standardreihenfolge), für SPS `rack`/`slot`.

## Treiber

| Gerät | Treiber | Lesen | Update |
|---|---|---|---|
| Balluff IO-Link-Master | `balluff_update.py` | ja | ja |
| ads-tec Firewall/Router | `firewall_update.py`, `jsonrpcdevice.py` | ja (Firmwareversion) | ja |
| Siemens SPS | `snap7` (python-snap7 2.x) | ja | **nein**; STOP/RUN wird nie automatisch ausgelöst |

Standardreihenfolge: Feldgeräte (Balluff) → Steuerungen → Netzwerkinfrastruktur (ads-tec) zuletzt.

## Tests

```powershell
& "$env:LOCALAPPDATA\ADS-TEC-Security-Manager\venv\Scripts\python.exe" -m pip install -r backend\requirements-dev.txt
& "$env:LOCALAPPDATA\ADS-TEC-Security-Manager\venv\Scripts\python.exe" -m pytest tests
cd frontend; npm test; npm run build
```
