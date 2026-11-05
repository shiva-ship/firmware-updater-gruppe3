from __future__ import annotations

import os
import struct

from fastapi.testclient import TestClient

from .conftest import DEVICE_PASSWORD, MASTER_PASSWORD, build_sample_kdbx, login, upload


def _stored_files(settings) -> list[str]:
    return sorted(os.listdir(settings.upload_dir)) if settings.upload_dir.exists() else []


# ---------------------------------------------------------------- Upload


def test_upload_requires_authentication(client, sample_kdbx):
    response = client.post("/api/databases", content=sample_kdbx.read_bytes(), headers={"X-File-Name": "a.kdbx"})
    assert response.status_code == 401


def test_upload_requires_csrf(client, csrf, sample_kdbx):
    response = upload(client, "falsch", sample_kdbx.read_bytes())
    assert response.status_code == 403


def test_upload_valid_file(client, csrf, sample_kdbx, settings):
    response = upload(client, csrf, sample_kdbx.read_bytes(), filename="Geräte Werk.kdbx")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["filename"] == "Geräte Werk.kdbx"
    assert body["size_bytes"] == sample_kdbx.stat().st_size
    assert body["status"] == "locked"
    files = _stored_files(settings)
    assert len(files) == 1 and files[0].endswith(".kdbx")
    assert "Geräte" not in files[0]  # zufälliger Name, nicht der Originalname


def test_upload_rejects_random_bytes(client, csrf, settings):
    response = upload(client, csrf, os.urandom(4096))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_database_file"
    assert _stored_files(settings) == []


def test_upload_rejects_wrong_extension(client, csrf, sample_kdbx):
    response = upload(client, csrf, sample_kdbx.read_bytes(), filename="geraete.txt")
    assert response.status_code == 400


def test_upload_rejects_keepass1_and_truncated(client, csrf, settings):
    kdb1 = struct.pack("<IIHH", 0x9AA2D903, 0xB54BFB65, 0, 3) + b"\0" * 100
    assert upload(client, csrf, kdb1).status_code == 400
    assert upload(client, csrf, b"\x03\xd9\xa2").status_code == 400
    assert upload(client, csrf, b"").status_code == 400
    assert _stored_files(settings) == []


def test_upload_rejects_unsupported_version(client, csrf):
    v5 = struct.pack("<IIHH", 0x9AA2D903, 0xB54BFB67, 0, 5) + b"\0" * 100
    assert upload(client, csrf, v5).status_code == 400


def test_upload_size_limit(client, csrf, settings):
    header = struct.pack("<IIHH", 0x9AA2D903, 0xB54BFB67, 1, 4)
    response = upload(client, csrf, header + b"\0" * (settings.max_upload_bytes + 1))
    assert response.status_code == 413
    assert _stored_files(settings) == []


def test_upload_limit_per_session(client, csrf, sample_kdbx):
    for _ in range(3):  # max_databases_per_session=3
        assert upload(client, csrf, sample_kdbx.read_bytes()).status_code == 201
    response = upload(client, csrf, sample_kdbx.read_bytes())
    assert response.status_code == 409


def test_corrupted_kdbx_with_valid_header(client, csrf, sample_kdbx):
    data = bytearray(sample_kdbx.read_bytes())
    data[200:400] = os.urandom(200)
    db_id = upload(client, csrf, bytes(data)).json()["id"]
    response = client.post(f"/api/databases/{db_id}/unlock", json={"master_password": MASTER_PASSWORD}, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 400
    assert response.json()["error"]["code"] in {"invalid_database_file", "invalid_master_password"}


# ---------------------------------------------------------------- Entsperren


def _unlock(client, csrf, db_id, password=MASTER_PASSWORD):
    return client.post(f"/api/databases/{db_id}/refresh", json={"master_password": password}, headers={"X-CSRF-Token": csrf})


def test_wrong_master_password(client, csrf, sample_kdbx):
    db_id = upload(client, csrf, sample_kdbx.read_bytes()).json()["id"]
    response = _unlock(client, csrf, db_id, "falsches-masterpasswort")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_master_password"
    assert "falsches-masterpasswort" not in response.text
    # Anmeldung bleibt bestehen, Datenbank bleibt gesperrt
    assert client.get("/api/auth/session").json()["authenticated"] is True
    assert client.get(f"/api/databases/{db_id}/tree").status_code == 409


def test_unlock_rate_limit(client, csrf, sample_kdbx):
    db_id = upload(client, csrf, sample_kdbx.read_bytes()).json()["id"]
    for _ in range(3):
        assert _unlock(client, csrf, db_id, "falsch").status_code == 400
    assert _unlock(client, csrf, db_id).status_code == 429


def test_unlock_requires_csrf(client, csrf, sample_kdbx):
    db_id = upload(client, csrf, sample_kdbx.read_bytes()).json()["id"]
    response = client.post(f"/api/databases/{db_id}/unlock", json={"master_password": MASTER_PASSWORD})
    assert response.status_code == 403


# ---------------------------------------------------------------- Baumstruktur


def _find_group(node, name):
    if node["name"] == name:
        return node
    for g in node["groups"]:
        found = _find_group(g, name)
        if found:
            return found
    return None


def _open_tree(client, csrf, kdbx_path):
    db_id = upload(client, csrf, kdbx_path.read_bytes()).json()["id"]
    unlock = _unlock(client, csrf, db_id)
    assert unlock.status_code == 200, unlock.text
    assert unlock.json()["status"] == "unlocked"
    response = client.get(f"/api/databases/{db_id}/tree")
    assert response.status_code == 200
    return db_id, response


def test_tree_nested_groups_and_serials(client, csrf, sample_kdbx):
    _, response = _open_tree(client, csrf, sample_kdbx)
    tree = response.json()
    root = tree["root"]

    assert [g["name"] for g in root["groups"]] == ["ADS-TEC", "Balluff", "Weidmüller", "Murrelektronik", "Siemens"]

    ads = _find_group(root, "ADS-TEC")
    assert {e["title"]: e["serial_number"] for e in ads["entries"]} == {"IRF3401": "AX20237856", "IRF3801": "AX20229229"}
    assert ads["entry_count"] == 2
    assert ads["total_entry_count"] == 3

    linie = _find_group(root, "Linie 7")
    assert linie is not None
    assert linie["entries"][0] == {"id": linie["entries"][0]["id"], "title": "IRF2000", "serial_number": "AX19990001", "serial_source": "field"}
    assert _find_group(root, "Halle 3")["total_entry_count"] == 1

    assert _find_group(root, "Siemens") == {**_find_group(root, "Siemens"), "entries": [], "groups": [], "entry_count": 0}
    assert tree["stats"] == {"groups": 8, "entries": 6, "entries_without_serial": 2, "serials_from_notes": 1}


def test_tree_serial_from_notes(client, csrf, sample_kdbx):
    _, response = _open_tree(client, csrf, sample_kdbx)
    balluff = {e["title"]: e for e in _find_group(response.json()["root"], "Balluff")["entries"]}
    assert balluff["BNI XG5"]["serial_number"] == "BX55667788"
    assert balluff["BNI XG5"]["serial_source"] == "notes"
    assert balluff["BNI XG3"]["serial_source"] is None
    ads = {e["title"]: e for e in _find_group(response.json()["root"], "ADS-TEC")["entries"]}
    assert ads["IRF3401"]["serial_source"] == "field"
    # Notizinhalt selbst wird nicht ausgeliefert
    assert "Schaltschrank" not in response.text


def test_refresh_rereads_and_keeps_tree_on_wrong_password(client, csrf, sample_kdbx):
    db_id, _ = _open_tree(client, csrf, sample_kdbx)
    again = client.post(f"/api/databases/{db_id}/refresh", json={"master_password": MASTER_PASSWORD}, headers={"X-CSRF-Token": csrf})
    assert again.status_code == 200 and again.json()["status"] == "unlocked"
    wrong = client.post(f"/api/databases/{db_id}/refresh", json={"master_password": "falsch"}, headers={"X-CSRF-Token": csrf})
    assert wrong.status_code == 400
    assert client.get(f"/api/databases/{db_id}/tree").status_code == 200


def test_tree_missing_serials_are_null(client, csrf, sample_kdbx):
    _, response = _open_tree(client, csrf, sample_kdbx)
    root = response.json()["root"]
    assert _find_group(root, "Balluff")["entries"][0]["serial_number"] is None
    assert _find_group(root, "Weidmüller")["entries"][0]["serial_number"] is None


def test_tree_contains_no_secrets(client, csrf, sample_kdbx):
    _, response = _open_tree(client, csrf, sample_kdbx)
    text = response.text
    assert DEVICE_PASSWORD not in text
    assert MASTER_PASSWORD not in text
    assert "192.168.0.1" not in text
    assert "10.0.0.5" not in text
    assert '"password"' not in text and '"username"' not in text


def test_recycle_bin_hidden(client, csrf, tmp_path):
    from pykeepass import PyKeePass

    path = build_sample_kdbx(tmp_path / "rb.kdbx")
    kp = PyKeePass(str(path), password=MASTER_PASSWORD)
    kp.trash_group(kp.find_groups(name="Siemens", first=True))
    kp.save()
    _, response = _open_tree(client, csrf, path)
    names = [g["name"] for g in response.json()["root"]["groups"]]
    assert "Siemens" not in names
    assert "Recycle Bin" not in names and "Papierkorb" not in names


# ---------------------------------------------------------------- Isolation & Aufräumen


def test_databases_are_isolated_per_user(app, client, csrf, sample_kdbx):
    db_id, _ = _open_tree(client, csrf, sample_kdbx)
    app.state.services.users.create_user("operator", "Anderes-Passwort-77")
    # Ohne Kontextmanager: kein zweiter Lifespan-Start (der würde alle Sitzungen beenden).
    other = TestClient(app)
    other_csrf = login(other, "operator", "Anderes-Passwort-77")
    assert other.get(f"/api/databases/{db_id}/tree").status_code == 404
    assert other.get("/api/databases").json()["databases"] == []
    assert other.delete(f"/api/databases/{db_id}", headers={"X-CSRF-Token": other_csrf}).status_code == 404
    assert client.get(f"/api/databases/{db_id}/tree").status_code == 200


def test_close_database_deletes_file(client, csrf, sample_kdbx, settings):
    db_id, _ = _open_tree(client, csrf, sample_kdbx)
    assert len(_stored_files(settings)) == 1
    assert client.delete(f"/api/databases/{db_id}", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert _stored_files(settings) == []
    assert client.get(f"/api/databases/{db_id}/tree").status_code == 404


def test_logout_deletes_all_files(client, csrf, sample_kdbx, settings):
    upload(client, csrf, sample_kdbx.read_bytes())
    upload(client, csrf, sample_kdbx.read_bytes())
    assert len(_stored_files(settings)) == 2
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert _stored_files(settings) == []


def test_relogin_ends_previous_session_databases(client, csrf, sample_kdbx, settings):
    upload(client, csrf, sample_kdbx.read_bytes())
    login(client)  # gleiche Cookie-Jar → alte Sitzung wird beendet
    assert _stored_files(settings) == []
