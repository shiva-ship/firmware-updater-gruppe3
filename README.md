# ADS-TEC Security Manager

**Industrial Device & Credential Management**: eine lokale Webanwendung, mit der sich KeePass-Datenbanken (KDBX) sicher öffnen lassen. Gruppen, Geräte und Seriennummern werden als interaktive Baumstruktur angezeigt.

Version 0.1 umfasst: Login → KDBX-Upload → Masterpasswort → Entschlüsselung → dynamische Baumstruktur → Datenbank schließen / Logout.

---

## Inhalt

1. [Voraussetzungen](#1-voraussetzungen)
2. [Einrichtung unter Windows PowerShell](#2-einrichtung-unter-windows-powershell)
3. [Starten](#3-starten)
4. [Entwicklungsmodus](#4-entwicklungsmodus-hot-reload)
5. [Tests](#5-tests)
6. [Benutzerverwaltung (CLI)](#6-benutzerverwaltung-cli)
7. [KeePass-Datenbank vorbereiten](#7-keepass-datenbank-vorbereiten)
8. [REST-API](#8-rest-api)
9. [Sicherheitskonzept](#9-sicherheitskonzept)
10. [Projektstruktur & Erweiterbarkeit](#10-projektstruktur--erweiterbarkeit)
11. [LAN-Betrieb (später)](#11-lan-betrieb-später-nur-https)
12. [Fehlerbehebung](#12-fehlerbehebung)

---

## 1. Voraussetzungen

| Komponente | Version | Installation |
|---|---|---|
| Python (offiziell, python.org) | 3.11 – 3.13 | `winget install Python.Python.3.12 --scope user` |
| Node.js | 20.19+ oder 22+ | `winget install OpenJS.NodeJS.LTS` |

> **Wichtig:** Ein Python aus MSYS2/Cygwin (z. B. `C:\msys64\ucrt64\bin\python.exe`) funktioniert **nicht**: Es kann die Binärpakete `pydantic-core`, `argon2-cffi` und `lxml` nicht installieren. Prüfen Sie mit `(Get-Command python).Source`, welches Python aktiv ist. Das Setup-Skript sucht automatisch nach dem offiziellen Python.

Zur Laufzeit lädt die Anwendung nichts von externen CDNs. Schriften (Inter, JetBrains Mono) und Icons (Lucide) sind im Build enthalten.

## 2. Einrichtung unter Windows PowerShell

```powershell
cd "$HOME\ads-tec-security-manager"

# Einmalig: venv anlegen, Abhängigkeiten installieren, Frontend bauen
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1

# Optional: Konfiguration anpassen (Standardwerte sind sicher)
Copy-Item .env.example .env

# Ersten Administrator anlegen (das Passwort wird verdeckt abgefragt)
.\.venv\Scripts\python.exe -m backend.cli create-admin --username admin
```

<details>
<summary>Manuelle Einrichtung ohne Skript</summary>

```powershell
cd "$HOME\ads-tec-security-manager"
py -3.12 -m venv .venv            # oder: & "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt

cd frontend
npm install
npm run build
cd ..
```
</details>

Passwortrichtlinie für Benutzer: mindestens 12 Zeichen, mindestens drei Zeichenklassen, der Benutzername darf nicht enthalten sein. Ein voreingestelltes Administratorkonto gibt es nicht.

## 3. Starten

```powershell
cd "$HOME\ads-tec-security-manager"
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
# alternativ:  .\.venv\Scripts\python.exe -m backend
```

Danach im Browser **http://127.0.0.1:8000** öffnen. Beenden mit `Strg+C`.

Der Server lauscht standardmäßig nur auf `127.0.0.1`. Frontend und API laufen unter derselben Origin, CORS ist daher nicht nötig.

## 4. Entwicklungsmodus (Hot-Reload)

Zwei PowerShell-Fenster:

```powershell
# Fenster 1 – Backend
cd "$HOME\ads-tec-security-manager"
$env:ASM_ENVIRONMENT = "development"   # aktiviert nur /api/docs
.\.venv\Scripts\python.exe -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

```powershell
# Fenster 2 – Frontend (Vite, leitet /api an das Backend weiter)
cd "$HOME\ads-tec-security-manager\frontend"
npm run dev
```

Frontend unter **http://127.0.0.1:5173**, API-Doku unter http://127.0.0.1:8000/api/docs (nur im Development-Modus).

> Hinweis: Mit `--reload` startet das Backend bei jeder Codeänderung neu. Dabei werden alle Sitzungen und hochgeladenen Dateien verworfen (siehe Sicherheitskonzept), Sie müssen sich also danach neu anmelden.

## 5. Tests

```powershell
cd "$HOME\ads-tec-security-manager"
.\.venv\Scripts\python.exe -m pytest
```

Abgedeckt sind unter anderem:

| Bereich | Tests |
|---|---|
| Login | Erfolg, HttpOnly/SameSite-Cookie, falsches Passwort, unbekannter Benutzer, Rate-Limit (429), Logout + CSRF, Argon2id-Hash, Passwortrichtlinie, Sitzungsablauf, Origin- und Host-Prüfung |
| Ungültige KeePass-Dateien | Zufallsbytes, falsche Endung, KeePass 1.x, abgeschnittene/leere Datei, nicht unterstützte Version, Größenlimit, beschädigter Inhalt bei gültigem Header |
| Falsche Masterpasswörter | Fehlercode, Anmeldung bleibt bestehen, Datenbank bleibt gesperrt, Rate-Limit beim Entsperren |
| Verschachtelte Gruppen | 4 Ebenen im API-Test, 12 Ebenen im Unit-Test, Zählwerte direkt/rekursiv, leere Gruppen, Papierkorb ausgeblendet |
| Fehlende Seriennummern | `null` statt erfundener Werte, nur Leerzeichen, keine Ableitung aus IP/Notizen, alternative Feldnamen |
| Datenschutz | keine Geräte-/Masterpasswörter, URLs oder Notizen in der API, Isolation zwischen Benutzern, Löschen der Dateien beim Schließen/Logout/Neu-Login |

Die Tests erzeugen ihre KDBX-Dateien selbst mit pykeepass in temporären Verzeichnissen. Im Repository liegen keine KeePass-Dateien.

## 6. Benutzerverwaltung (CLI)

```powershell
.\.venv\Scripts\python.exe -m backend.cli create-admin   --username admin
.\.venv\Scripts\python.exe -m backend.cli reset-password --username admin   # beendet alle Sitzungen des Benutzers
.\.venv\Scripts\python.exe -m backend.cli deactivate     --username admin
.\.venv\Scripts\python.exe -m backend.cli activate       --username admin
.\.venv\Scripts\python.exe -m backend.cli list-users
```

Passwörter werden nie als Kommandozeilenargument übergeben, sondern interaktiv und verdeckt abgefragt. So landen sie nicht in der PowerShell-Historie.

## 7. KeePass-Datenbank vorbereiten

Die Baumstruktur folgt exakt der Gruppenhierarchie der KDBX-Datei. Jeder Eintrag erscheint als Gerät, sein **Titel** wird als Gerätename verwendet.

**Seriennummer:** In KeePass unter *Eintrag bearbeiten → Erweitert → Zeichenfolgenfelder* ein Feld anlegen. Unterstützte Namen, in dieser Priorität:

1. `SerialNumber`
2. `Serialnummer`
3. `serial_number`

Ist keines dieser Felder vorhanden oder ist es leer, zeigt die Oberfläche **„Nicht hinterlegt“**. Seriennummern werden nie erraten oder aus anderen Feldern (IP, Notizen) abgeleitet. Der KeePass-Papierkorb wird nicht angezeigt.

Demo-Datenbank mit Fantasiedaten erzeugen (außerhalb des Repositories ablegen):

```powershell
.\.venv\Scripts\python.exe scripts\make-demo-kdbx.py "$env:USERPROFILE\Desktop\demo.kdbx"
```

Unterstützt werden KDBX 3.1 und KDBX 4.x mit Masterpasswort. Schlüsseldateien sind in Version 0.1 noch nicht unterstützt.

## 8. REST-API

Alle Antworten sind JSON. Fehler haben die Form `{"error": {"code": "...", "message": "..."}}`.
Zustandsändernde Requests benötigen den Header `X-CSRF-Token` (aus `/api/auth/session` bzw. der Login-Antwort).

| Methode | Pfad | Zweck | Auth | CSRF |
|---|---|---|---|---|
| `POST` | `/api/auth/login` | Anmelden `{username, password}` → Sitzung + CSRF-Token | – | Origin-Prüfung |
| `POST` | `/api/auth/logout` | Abmelden, schließt alle Datenbanken der Sitzung | ✓ | ✓ |
| `GET` | `/api/auth/session` | Aktuelle Sitzung prüfen | – | – |
| `GET` | `/api/databases` | Geöffnete Datenbanken der Sitzung + Limits | ✓ | – |
| `POST` | `/api/databases` | KDBX hochladen (Body: Rohdaten `application/octet-stream`, Header `X-File-Name`: URL-kodierter Dateiname) | ✓ | ✓ |
| `POST` | `/api/databases/{id}/unlock` | Entsperren `{master_password}` | ✓ | ✓ |
| `GET` | `/api/databases/{id}/tree` | Gruppenhierarchie (nur Metadaten) | ✓ | – |
| `DELETE` | `/api/databases/{id}` | Datenbank schließen, Datei löschen | ✓ | ✓ |
| `GET` | `/api/health` | Health-Check | – | – |

Beispiel `GET /api/databases/{id}/tree`:

```json
{
  "database": { "id": "…", "filename": "geraete.kdbx", "size_bytes": 2021, "status": "unlocked", "uploaded_at": "…", "unlocked_at": "…" },
  "root": {
    "id": "…", "name": "Root", "entry_count": 0, "total_entry_count": 5,
    "entries": [],
    "groups": [
      { "id": "…", "name": "ADS-TEC", "entry_count": 2, "total_entry_count": 3,
        "entries": [ { "id": "…", "title": "IRF3401", "serial_number": "AX20237856" } ],
        "groups": [ … ] }
    ]
  },
  "stats": { "groups": 8, "entries": 5, "entries_without_serial": 2 }
}
```

Benutzernamen, Passwörter, URLs und Notizen der KeePass-Einträge sind **nicht** Teil der API.

## 9. Sicherheitskonzept

| Anforderung | Umsetzung |
|---|---|
| Passwort-Speicherung | Argon2id (64 MiB, t=3, p=4) über `argon2-cffi`; automatisches Rehash bei Parameteränderung |
| Sitzungen | Zufallstoken (256 Bit) im **HttpOnly**-, **SameSite=Strict**-Cookie; in SQLite liegt nur der SHA-256-Hash. Idle-Timeout 30 min, absolut 8 h. Bei TLS automatisch `Secure` |
| CSRF | Synchronizer-Token pro Sitzung (Header `X-CSRF-Token`, nur im JS-Speicher) + Ablehnung fremder `Origin`-Header + SameSite=Strict |
| Session Fixation | Beim Login wird eine vorhandene Sitzung beendet und eine neue erzeugt |
| Brute-Force | Login: 5 Fehlversuche / 15 min pro Benutzername (20 pro IP) → 15 min Sperre, `429` + `Retry-After`. Masterpasswort: 5 Versuche / 5 min pro Benutzer+Datenbank. Gleiche Fehlermeldung und Laufzeit bei unbekanntem Benutzer |
| Masterpasswort | Nur als `SecretStr` im Request, wird direkt an pykeepass übergeben und danach verworfen. Kein Logging, keine Speicherung, keine Rückgabe. Validierungsfehler geben **keine** Eingabewerte zurück |
| Entschlüsselte Daten | Nach dem Entsperren wird nur der Metadatenbaum im RAM gehalten. Das `PyKeePass`-Objekt mit den Gerätepasswörtern wird sofort verworfen |
| Uploads | Rohdaten werden direkt in `%LOCALAPPDATA%\ADS-TEC-Security-Manager\uploads` gestreamt (kein System-Temp), unter einer zufälligen UUID gespeichert. Prüfung von Endung, KDBX-Signatur und Version sowie Größenlimit (20 MB) beim Streamen |
| Zuordnung | Jede Datenbank ist an genau eine Sitzung **und** einen Benutzer gebunden; fremde IDs liefern `404` |
| Aufräumen | Dateien werden gelöscht bei: Schließen, Logout, Neu-Login, Sitzungsablauf (Hintergrundtask jede Minute), Server-Stopp und Server-Start (verwaiste Dateien) |
| XSS | React escaped alle Ausgaben, kein `dangerouslySetInnerHTML`; strikte CSP `script-src 'self'` ohne `unsafe-inline`; `X-Content-Type-Options`, `X-Frame-Options: DENY`, `frame-ancestors 'none'` |
| Browser-Storage | Kein `localStorage`/`sessionStorage`. Das CSRF-Token liegt nur im Arbeitsspeicher |
| Host-Header | `TrustedHostMiddleware` (Schutz gegen DNS-Rebinding) |
| Produktivbetrieb | `debug=False`, kein Reload, OpenAPI/Swagger deaktiviert, kein `Server`-Header, `Cache-Control: no-store` für API |
| Netzwerk | Standard `127.0.0.1`. Nicht-Loopback-Adressen verweigert der Server ohne TLS-Zertifikat |
| Git | `.gitignore` schließt `*.kdbx`, `.env`, Datenbanken, Zertifikate und Laufzeitdaten aus |

**Bewusste Einschränkungen in Version 0.1:**

- Der Sitzungszustand der KeePass-Datenbanken liegt im Prozessspeicher. Deshalb läuft genau ein Worker, und nach einem Neustart ist eine erneute Anmeldung nötig.
- Python kann Strings nicht sicher aus dem Speicher löschen. Das Masterpasswort bleibt daher bis zur Garbage Collection im RAM des Prozesses.
- Der Rate-Limiter ist in-memory. Eine Sperre pro Benutzername kann von Dritten ausgelöst werden; lokal ist das akzeptabel, im LAN gehört Netzwerk-Zugriffskontrolle davor.

## 10. Projektstruktur & Erweiterbarkeit

```
ads-tec-security-manager/
├── backend/
│   ├── __main__.py            # Start: python -m backend (Loopback/TLS-Prüfung, uvicorn)
│   ├── main.py                # App-Factory, Security-Middleware, Fehlerbehandlung, Lifespan
│   ├── config.py              # Einstellungen (ASM_* / .env)
│   ├── errors.py              # Fachliche Fehler mit stabilen Codes
│   ├── db.py                  # SQLite-Schema (users, sessions)
│   ├── cli.py                 # Benutzerverwaltung
│   ├── api/
│   │   ├── auth.py            # /api/auth/*
│   │   ├── databases.py       # /api/databases/*
│   │   ├── deps.py            # Sitzung, CSRF, Dienste
│   │   └── schemas.py         # Pydantic-Modelle (nur Metadaten)
│   └── services/
│       ├── auth/              # passwords (Argon2id), users, sessions, rate_limit
│       └── keepass/           # storage (Upload/Validierung), tree (Baum), manager (Sitzungen)
├── frontend/
│   └── src/
│       ├── api/               # Fetch-Client (CSRF im Speicher), Typen
│       ├── components/        # AppShell, TreeView, UI-Bausteine
│       ├── lib/               # Baumfilter, Formatierung
│       └── pages/             # Login, Upload, Unlock, Tree
├── tests/                     # pytest
├── scripts/                   # setup.ps1, start.ps1, make-demo-kdbx.py
├── .env.example
└── README.md
```

**Vorbereitet für spätere Funktionen** (Firewall-Anbindung, Geräte-APIs, Firmware, CVE-Analyse):

- Neue Fachmodule kommen als `backend/services/<modul>/` mit eigenem Router in `backend/api/` dazu und werden in `backend/api/__init__.py` registriert.
- Benutzer haben ein `role`-Feld, auf dessen Basis sich Berechtigungen ergänzen lassen.
- Jeder Eintrag hat eine stabile KeePass-UUID (`id`), über die Folgefunktionen Geräte adressieren können. Zugangsdaten werden dann bei Bedarf serverseitig aus der weiterhin vorliegenden KDBX-Datei gelesen und nie an das Frontend gegeben.
- `KeePassSessionManager` verwaltet bereits mehrere Datenbanken pro Sitzung.

## 11. LAN-Betrieb (später, nur HTTPS)

```powershell
# .env
ASM_HOST=0.0.0.0
ASM_ALLOWED_HOSTS=security-manager.firma.local
ASM_TLS_CERTFILE=C:\certs\security-manager.crt
ASM_TLS_KEYFILE=C:\certs\security-manager.key
```

Mit TLS setzt der Server automatisch `Secure`-Cookies und HSTS. Ohne Zertifikat verweigert er den Start auf Nicht-Loopback-Adressen. Zusätzlich empfohlen: Windows-Firewall-Regel nur für das Admin-VLAN, interne CA statt selbstsignierter Zertifikate, VPN oder Reverse-Proxy mit Client-Zertifikaten.

## 12. Fehlerbehebung

| Problem | Lösung |
|---|---|
| `Ausführung von Skripts ist auf diesem System deaktiviert` | Skripte mit `powershell -ExecutionPolicy Bypass -File …` starten |
| `pip install` scheitert an `pydantic-core`/`lxml` (Rust/Compiler-Fehler) | Es wird ein MSYS2/Cygwin-Python verwendet. Offizielles Python installieren und `.venv` löschen, dann `setup.ps1` erneut ausführen |
| `.venv\Scripts\python.exe` fehlt, es gibt aber `.venv\bin` | Die venv wurde mit MSYS2-Python erzeugt: löschen und neu einrichten |
| Weiße Seite / nur API | Frontend-Build fehlt: `cd frontend; npm run build` |
| „Zu viele Fehlversuche“ | Sperrzeit abwarten oder Server neu starten (In-Memory-Limiter) |
| Nach Neustart abgemeldet | Gewollt: Beim Start werden alle Sitzungen und temporären Dateien verworfen |
| Port 8000 belegt | `$env:ASM_PORT = "8010"` vor dem Start setzen |
| Build/Tests sehr langsam | Echtzeit-Virenscan auf `node_modules` / `.venv` verlangsamt Windows stark. Gegebenenfalls einen Ausschluss für das Projektverzeichnis einrichten (in Absprache mit der IT) |
