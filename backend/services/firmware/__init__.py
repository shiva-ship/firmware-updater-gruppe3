"""Firmwareupdates – noch NICHT implementiert (geplant für eine spätere Version).

Verbindliche Freigabekette, bevor ein Update gestartet werden darf:

1. Geräteauswahl        – ein konkretes Gerät (KeePass-UUID) aus der entsperrten Datenbank
2. Treiberprüfung       – passender Treiber für Gerätetyp vorhanden und signiert
3. Kompatibilitätsprüfung – Firmware-Version passt zu Hardware-Revision/Seriennummer
4. Ausdrückliche Bestätigung – separater Bestätigungsschritt im Frontend
5. Masterpasswort       – ``KeePassSessionManager.verify_master_password`` (dasselbe Modal
                          wie „Aktualisieren“); Passwort wird nicht gespeichert/protokolliert

Erst wenn alle Schritte serverseitig in dieser Reihenfolge erfolgreich waren, darf ein
Update-Job angelegt werden. Gerätezugangsdaten werden dann ausschließlich serverseitig
aus der KDBX-Datei gelesen und nie an das Frontend übertragen.
"""
