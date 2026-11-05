# ADS-TEC Security Manager

Lokale Webanwendung: KeePass-Datei (`.kdbx`) hochladen → „Aktualisieren“ → Masterpasswort eingeben → Gruppen, Geräte und Seriennummern als Baum.

## Voraussetzungen (einmalig)

```powershell
winget install Python.Python.3.12 --scope user
winget install OpenJS.NodeJS.LTS
```

Wichtig: Es muss das **offizielle** Python sein, nicht MSYS2/Cygwin.

## Starten

```powershell
git clone -b security-manager https://github.com/shiva-ship/firmware-updater-gruppe3.git
cd firmware-updater-gruppe3
.\start.cmd
```

Beim ersten Start wird alles automatisch installiert (dauert ein paar Minuten). Danach öffnet sich der Browser:

- **Erster Start:** Administrator anlegen (Benutzername + Passwort, mind. 12 Zeichen)
- **Danach:** Mit diesem Konto anmelden

Adresse: http://127.0.0.1:8000. Zum Beenden das Fenster „ADS-TEC Security Manager“ schließen.

## Seriennummern

Werden gelesen aus dem KeePass-Feld `SerialNumber` (alternativ `Serialnummer`, `serial_number`) oder aus den Notizen, z. B. `Serial: AX20237856`, `S/N: …`, `Seriennummer: …`. Ohne Angabe steht dort „Nicht hinterlegt“.

## Hinweise

- Läuft nur lokal (`127.0.0.1`), KeePass-Dateien werden beim Schließen/Logout gelöscht.
- Masterpasswörter werden nicht gespeichert oder protokolliert.
- KeePass-Dateien (`*.kdbx`) niemals ins Repository committen.
