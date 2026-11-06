"""Kompletter Ablauf über die REST-API: Login → Upload → Entschlüsseln → Planen → Dry-Run → Freigabe → Update."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.db import Database
from backend.main import create_app
from backend.services.auth import UserRepository
from backend.services.devices import DeviceInfo, UpdateResult
from tests.conftest import TEST_MASTER_PASSWORD

ADMIN_PASSWORD = "Leitstand-Zugang-123!"
FW_NAME = "Ads-tec-IRF3xxx-2.3.4-SVN-R1.B-1.bin"


class FixedSimulator:
    """Deterministische Simulation: alle Geräte online, ads-tec auf 2.3.1."""

    def __init__(self):
        self.installed: dict[str, str] = {}

    def read_info(self, node):
        if node.device_type is None:
            return DeviceInfo(connection="not_checked", simulated=True)
        version = self.installed.get(node.id, {"adstec": "2.3.1", "balluff": "1.0.0", "siemens": "V4.5.2"}[node.device_type])
        return DeviceInfo(connection="online", installed_version=version, model="IRF3401", serial_number=node.serial_number,
                          simulated=True)

    def update(self, node, _path, target, progress):
        progress("simuliert", 0.5)
        self.installed[node.id] = target
        return UpdateResult(previous_version="2.3.1", message="simuliert")


def _forbidden(*_args, **_kwargs):
    raise AssertionError("Im DEMO-Modus darf kein echter Gerätetreiber aufgerufen werden.")


def make_client(tmp_path, firmware_dir, mode="demo"):
    settings = Settings(
        data_dir=tmp_path / "data", firmware_dir=firmware_dir, allowed_hosts="testserver", device_mode=mode,
        demo_step_seconds=0, environment="development",
    )
    db = Database(settings.users_db_path)
    db.init_schema()
    UserRepository(db).create_user("admin", ADMIN_PASSWORD)
    app = create_app(settings)
    return app, TestClient(app)


def login(client) -> dict:
    r = client.post("/api/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def upload_and_unlock(client, h, kdbx_file) -> tuple[str, dict]:
    r = client.post("/api/databases", content=kdbx_file.read_bytes(),
                    headers={**h, "Content-Type": "application/octet-stream", "X-File-Name": "test.kdbx"})
    assert r.status_code == 201, r.text
    db_id = r.json()["id"]
    # Vor "Aktualisieren" gibt es keinen Baum
    assert client.get(f"/api/databases/{db_id}/tree").status_code == 409
    assert client.post(f"/api/databases/{db_id}/refresh", json={"master_password": "falsch"}, headers=h).status_code == 400
    r = client.post(f"/api/databases/{db_id}/refresh", json={"master_password": TEST_MASTER_PASSWORD}, headers=h)
    assert r.status_code == 200
    tree = client.get(f"/api/databases/{db_id}/tree")
    assert tree.status_code == 200
    return db_id, tree.json()


def entries_of(group, acc=None):
    acc = [] if acc is None else acc
    acc.extend(group["entries"])
    for g in group["groups"]:
        entries_of(g, acc)
    return acc


def wait_job(client, job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/update-jobs/{job_id}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("Auftrag nicht beendet")


def test_demo_end_to_end(tmp_path, kdbx_file, firmware_dir):
    app, client = make_client(tmp_path, firmware_dir)
    with client:
        services = app.state.services
        services.updates.simulator = FixedSimulator()
        # Echte Treiber werden durch Attrappen ersetzt, die bei jedem Aufruf fehlschlagen.
        for adapter in services.updates.adapters.values():
            adapter.read_info = adapter.update = _forbidden  # type: ignore[method-assign]
        h = login(client)
        db_id, tree = upload_and_unlock(client, h, kdbx_file)

        # Keine Zugangsdaten im Browser
        for secret in ("fw-secret", "bl-secret", "geheim123"):
            assert secret not in str(tree)
        entries = {e["title"]: e for e in entries_of(tree["root"])}
        assert tree["stats"]["duplicate_serials"] == 2
        fw = entries["Firewall Halle 1"]
        assert fw["serial_number"] == "AX20339256" and fw["host"] == "192.168.0.1"

        notes = client.get(f"/api/databases/{db_id}/entries/{entries['Master Linie 1']['id']}/notes").json()
        assert notes["redacted"] and "geheim123" not in notes["notes"]

        # Ohne Freigabe des Pakets ist nichts bereit
        all_ids = [e["id"] for e in entries.values()]
        plan = client.post(f"/api/databases/{db_id}/update-plans", json={"entry_ids": all_ids}, headers=h).json()
        assert plan["counts"]["ready"] == 0

        r = client.post("/api/firmware/packages/release",
                        json={"name": FW_NAME, "version": "2.3.4", "models": ["IRF3*"], "confirm": True}, headers=h)
        assert r.status_code == 200 and r.json()["status"] == "released"

        plan = client.post(f"/api/databases/{db_id}/update-plans", json={"entry_ids": all_ids}, headers=h).json()
        by_title = {i["title"]: i for i in plan["items"]}
        assert by_title["Firewall Halle 1"]["status"] == "ready"
        assert by_title["SPS Presse"]["status"] == "no_driver"
        assert by_title["Unbekanntes Gerät"]["status"] == "no_driver"
        assert by_title["Ohne Seriennummer"]["status"] == "no_driver"
        assert by_title["Master Linie 1"]["status"] == "blocked"  # Balluff-Paket nicht freigegeben
        # Firewall wird nach den Feldgeräten eingeplant
        positions = {i["title"]: i["position"] for i in plan["items"]}
        assert positions["Firewall Halle 1"] > positions["Master Linie 1"]

        # Auswahl löst kein Update aus; Dry-Run verändert nichts
        job = client.post(f"/api/update-plans/{plan['id']}/dry-run", headers=h).json()
        job = wait_job(client, job["id"])
        fw_item = next(i for i in job["items"] if i["title"] == "Firewall Halle 1")
        assert fw_item["state"] == "dry_run_ok"
        assert services.updates.simulator.installed == {}

        # Echtes (simuliertes) Update: Passwort erneut, dann Bestätigung
        assert client.post(f"/api/update-plans/{plan['id']}/execute",
                           json={"authorization_id": "x", "confirm": True}, headers=h).status_code == 403
        assert client.post(f"/api/update-plans/{plan['id']}/authorize",
                           json={"master_password": "falsch"}, headers=h).status_code == 400
        # Masterpasswort nur einmal: Freigabe ohne erneute Eingabe, solange die Frist läuft
        assert client.post(f"/api/update-plans/{plan['id']}/authorize", json={}, headers=h).status_code == 200
        auth = client.post(f"/api/update-plans/{plan['id']}/authorize",
                           json={"master_password": TEST_MASTER_PASSWORD}, headers=h)
        assert auth.status_code == 200 and TEST_MASTER_PASSWORD not in auth.text
        auth_id = auth.json()["authorization_id"]
        assert client.post(f"/api/update-plans/{plan['id']}/execute",
                           json={"authorization_id": auth_id, "confirm": False}, headers=h).status_code == 422
        r = client.post(f"/api/update-plans/{plan['id']}/execute",
                        json={"authorization_id": auth_id, "confirm": True}, headers=h)
        assert r.status_code == 200, r.text
        job = wait_job(client, r.json()["id"])
        fw_item = next(i for i in job["items"] if i["title"] == "Firewall Halle 1")
        assert fw_item["state"] == "succeeded" and fw_item["verified_version"] == "2.3.4"
        assert job["simulated"] is True
        assert all(i["state"] != "succeeded" for i in job["items"] if i["plan_status"] != "ready")

        # Freigabe ist nur einmal verwendbar
        assert client.post(f"/api/update-plans/{plan['id']}/execute",
                           json={"authorization_id": auth_id, "confirm": True}, headers=h).status_code == 403

        inventory = client.get(f"/api/databases/{db_id}/inventory").json()
        assert inventory["mode"] == "demo"
        assert inventory["devices"][fw["id"]]["installed_version"] == "2.3.4"


def test_csrf_and_auth_required(tmp_path, kdbx_file, firmware_dir):
    _, client = make_client(tmp_path, firmware_dir)
    with client:
        assert client.get("/api/firmware/packages").status_code == 401
        login(client)
        assert client.post("/api/firmware/packages/release",
                           json={"name": FW_NAME, "version": "2.3.4", "confirm": True}).status_code == 403


class RecordingAdapter:
    vendor = "adstec"
    label = "ads-tec"
    driver_module = "firewall_update"
    firmware_suffixes = (".bin",)
    supports_read = True
    supports_update = True
    requires_stop_run = False
    notes = ""

    def __init__(self):
        self.seen_passwords: list[str] = []
        self.version = "2.3.1"

    def driver_available(self):
        return True, None

    def read_info(self, access):
        self.seen_passwords.append(access.password)
        return DeviceInfo(connection="online", installed_version=self.version, model="IRF3401")

    def update(self, access, path, target, progress):
        assert path.name == FW_NAME
        progress("Upload", 0.5)
        self.version = target
        return UpdateResult(previous_version="2.3.1", message="ok")


def test_live_mode_uses_keepass_credentials_server_side(tmp_path, kdbx_file, firmware_dir):
    app, client = make_client(tmp_path, firmware_dir, mode="live")
    with client:
        adapter = RecordingAdapter()
        app.state.services.updates.adapters = {"adstec": adapter}
        h = login(client)
        db_id, tree = upload_and_unlock(client, h, kdbx_file)
        fw = next(e for e in entries_of(tree["root"]) if e["title"] == "Firewall Halle 1")


        client.post("/api/firmware/packages/release",
                    json={"name": FW_NAME, "version": "2.3.4", "models": [], "confirm": True}, headers=h)
        # Masterpasswort nur einmal (beim Entsperren): Vorbereiten nutzt die zwischengespeicherten Login-Daten
        r = client.post(f"/api/databases/{db_id}/update-plans", json={"entry_ids": [fw["id"]]}, headers=h)
        assert r.status_code == 200 and "fw-secret" not in r.text
        plan = r.json()
        assert plan["mode"] == "live" and plan["simulated"] is False
        assert plan["items"][0]["status"] == "ready", plan["items"][0]["blockers"]
        assert adapter.seen_passwords == ["fw-secret"]

        # Masterpasswort nur einmal: Zugangsdaten aus dem Vorbereiten werden für die Freigabe weiterverwendet
        assert plan["credentials_ready"] is True
        r = client.post(f"/api/update-plans/{plan['id']}/authorize", json={}, headers=h)
        assert r.status_code == 200 and "fw-secret" not in r.text
        auth_id = r.json()["authorization_id"]
        job = client.post(f"/api/update-plans/{plan['id']}/execute",
                          json={"authorization_id": auth_id, "confirm": True}, headers=h).json()
        job = wait_job(client, job["id"])
        assert job["state"] == "completed" and job["items"][0]["state"] == "succeeded"
        assert "fw-secret" not in str(job)


def test_live_credentials_expire(tmp_path, kdbx_file, firmware_dir):
    """Nach Ablauf der Frist wird das Masterpasswort wieder verlangt."""
    app, client = make_client(tmp_path, firmware_dir, mode="live")
    with client:
        now = [0.0]
        app.state.services.keepass._clock = lambda: now[0]
        app.state.services.updates.adapters = {"adstec": RecordingAdapter()}
        h = login(client)
        db_id, tree = upload_and_unlock(client, h, kdbx_file)
        fw = next(e for e in entries_of(tree["root"]) if e["title"] == "Firewall Halle 1")
        now[0] = 10_000  # Frist abgelaufen
        r = client.post(f"/api/databases/{db_id}/update-plans", json={"entry_ids": [fw["id"]]}, headers=h)
        assert r.status_code == 400 and r.json()["error"]["code"] == "master_password_required"
        r = client.post(f"/api/databases/{db_id}/update-plans",
                        json={"entry_ids": [fw["id"]], "master_password": TEST_MASTER_PASSWORD}, headers=h)
        assert r.status_code == 200
