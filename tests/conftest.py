from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pykeepass import create_database

from backend.config import Settings
from backend.main import create_app

ADMIN_USER = "admin"
ADMIN_PASSWORD = "Sehr-Sicheres-Passwort-42"
MASTER_PASSWORD = "Master#Passwort-2026"
DEVICE_PASSWORD = "geraete-geheimnis-XYZ-987"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        frontend_dist=tmp_path / "no-frontend",
        allowed_hosts="testserver,127.0.0.1,localhost",
        login_max_attempts=3,
        unlock_max_attempts=3,
        max_upload_bytes=1024 * 1024,
        max_databases_per_session=3,
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as c:
        app.state.services.users.create_user(ADMIN_USER, ADMIN_PASSWORD)
        yield c


def login(client: TestClient, username: str = ADMIN_USER, password: str = ADMIN_PASSWORD) -> str:
    """Meldet an und gibt das CSRF-Token zurück."""
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


@pytest.fixture
def csrf(client: TestClient) -> str:
    return login(client)


def build_sample_kdbx(path: Path, password: str = MASTER_PASSWORD) -> Path:
    """ADS-TEC-Beispielstruktur mit verschachtelten Gruppen, alternativen Feldnamen,
    fehlenden Seriennummern und leeren Gruppen."""
    kp = create_database(str(path), password=password)
    root = kp.root_group

    ads = kp.add_group(root, "ADS-TEC")
    irf3401 = kp.add_entry(ads, "IRF3401", "admin", DEVICE_PASSWORD, url="https://192.168.0.1")
    irf3401.set_custom_property("SerialNumber", "AX20237856")
    irf3801 = kp.add_entry(ads, "IRF3801", "admin", DEVICE_PASSWORD)
    irf3801.set_custom_property("Serialnummer", "AX20229229")

    werk = kp.add_group(ads, "Werk Nürtingen")
    halle = kp.add_group(werk, "Halle 3")
    linie = kp.add_group(halle, "Linie 7")
    deep = kp.add_entry(linie, "IRF2000", "service", DEVICE_PASSWORD)
    deep.set_custom_property("serial_number", "AX19990001")

    balluff = kp.add_group(root, "Balluff")
    kp.add_entry(balluff, "BNI XG3", "admin", DEVICE_PASSWORD, notes="IP: 10.0.0.5")  # keine Seriennummer
    kp.add_entry(
        balluff,
        "BNI XG5",
        "admin",
        DEVICE_PASSWORD,
        notes="Standort: Schaltschrank 4\nS/N: BX55667788\nIP: 10.0.0.6",  # Seriennummer nur in Notizen
    )

    weid = kp.add_group(root, "Weidmüller")
    uc20 = kp.add_entry(weid, "UC20-M3000", "admin", DEVICE_PASSWORD)
    uc20.set_custom_property("SerialNumber", "   ")  # nur Leerzeichen → nicht hinterlegt

    kp.add_group(root, "Murrelektronik")
    kp.add_group(root, "Siemens")
    kp.save()
    return path


@pytest.fixture
def sample_kdbx(tmp_path: Path) -> Path:
    return build_sample_kdbx(tmp_path / "geraete.kdbx")


def upload(client: TestClient, csrf: str, content: bytes, filename: str = "geraete.kdbx"):
    from urllib.parse import quote

    return client.post(
        "/api/databases",
        content=content,
        headers={"X-CSRF-Token": csrf, "X-File-Name": quote(filename), "Content-Type": "application/octet-stream"},
    )
