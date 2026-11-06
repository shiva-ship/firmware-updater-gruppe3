"""Updateplanung: Prüfungen, Status und Reihenfolge."""

from __future__ import annotations

from backend.services.devices import DeviceInfo, compare_versions, version_from_filename
from backend.services.firmware import FirmwarePackage, FirmwareUpdater
from backend.services.keepass import DeviceNode
from backend.services.updates import AdapterCapabilities, build_plan, plan_item

CAPS = {
    "adstec": AdapterCapabilities("adstec", "ads-tec", "firewall_update", True, True),
    "balluff": AdapterCapabilities("balluff", "Balluff", "balluff_update", True, True),
    "siemens": AdapterCapabilities("siemens", "Siemens", "snap7", False, True),
}


def node(id, vendor, serial="SN-" + "1", status="ok", **kw):
    return DeviceNode(id=id, title=f"Gerät {id}", serial_number=serial, serial_source="notes",
                      device_type=vendor, serial_status=status, **kw)


def pkg(vendor="adstec", version="2.3.4", status="released", models=None, verified=False):
    return FirmwarePackage(name=f"{vendor}.fw", size_bytes=1, vendor=vendor, sha256="a" * 64, filename_version=version,
                           status=status, version=version, models=models or [], vendor_checksum_verified=verified)


def online(version="2.3.1", model="IRF3401", serial=None):
    return DeviceInfo(connection="online", installed_version=version, model=model, serial_number=serial)


def test_versions():
    assert compare_versions("2.3.1", "2.3.4") == -1
    assert compare_versions("IRF3xxx-2.3.4-SVN", "2.3.4") == 0
    assert compare_versions("2.3", "2.3.0") == 0
    assert compare_versions("V4.6.1", "V4.5.2") == 1
    assert compare_versions("unbekannt", "2.3.4") is None
    assert version_from_filename("Ads-tec-IRF3xxx-2.3.4-SVN-R68479.B-189048.bin") == "2.3.4"
    assert version_from_filename("bni-ad.xg3.bff") is None


def test_ready_device():
    item = plan_item(node("1", "adstec"), ("Halle",), online(), CAPS["adstec"], [pkg(models=["IRF3*"])], simulated=True)
    assert item.status == "ready", item.blockers
    assert item.installed_version == "2.3.1" and item.target_version == "2.3.4"


def test_up_to_date_device():
    item = plan_item(node("1", "adstec"), (), online("2.3.4"), CAPS["adstec"], [pkg()], simulated=True)
    assert item.status == "up_to_date"


def test_missing_or_duplicate_serial_blocks():
    for status, serial in (("missing", None), ("duplicate", "DUP")):
        item = plan_item(node("1", "adstec", serial=serial, status=status), (), online(), CAPS["adstec"], [pkg()], simulated=True)
        assert item.status == "blocked"
        assert any("keine automatische Zuordnung" in b for b in item.blockers)


def test_serial_mismatch_on_device_blocks():
    item = plan_item(node("1", "adstec", serial="AX1"), (), online(serial="AX2"), CAPS["adstec"], [pkg()], simulated=False)
    assert item.status == "blocked"


def test_no_driver_is_never_ready():
    item = plan_item(node("1", "siemens"), (), online("V4.5.2"), CAPS["siemens"], [], simulated=True)
    assert item.status == "no_driver"
    item = plan_item(node("2", None), (), None, None, [], simulated=True)
    assert item.status == "no_driver"


def test_driver_not_loadable_blocks():
    caps = AdapterCapabilities("adstec", "ads-tec", "firewall_update", True, False, "ImportError")
    assert plan_item(node("1", "adstec"), (), online(), caps, [pkg()], simulated=False).status == "blocked"


def test_package_checks():
    cases = {
        "unreleased": [pkg(status="unreleased")],
        "hash": [pkg(status="hash_mismatch")],
        "none": [],
        "model": [pkg(models=["IRF2*"])],
    }
    for name, packages in cases.items():
        item = plan_item(node("1", "adstec"), (), online(), CAPS["adstec"], packages, simulated=True)
        assert item.status == "blocked", name


def test_unknown_model_blocks_if_models_restricted():
    item = plan_item(node("1", "adstec"), (), online(model=None), CAPS["adstec"], [pkg(models=["IRF3*"])], simulated=True)
    assert item.status == "blocked"
    item = plan_item(node("1", "adstec"), (), online(model=None), CAPS["adstec"], [pkg(models=[])], simulated=True)
    assert item.status == "ready"


def test_downgrade_and_offline_block():
    assert plan_item(node("1", "adstec"), (), online("2.4.0"), CAPS["adstec"], [pkg()], simulated=True).status == "blocked"
    offline = DeviceInfo(connection="offline", message="nicht erreichbar")
    assert plan_item(node("1", "adstec"), (), offline, CAPS["adstec"], [pkg()], simulated=True).status == "blocked"
    assert plan_item(node("1", "adstec"), (), None, CAPS["adstec"], [pkg()], simulated=True).status == "blocked"
    no_version = DeviceInfo(connection="online", installed_version=None, model="IRF3")
    assert plan_item(node("1", "adstec"), (), no_version, CAPS["adstec"], [pkg()], simulated=True).status == "blocked"


def test_order_field_devices_before_firewall_and_update_order_override():
    devices = [
        (node("fw", "adstec"), ("A",)),
        (node("b1", "balluff"), ("A",)),
        (node("plc", "siemens"), ("A",)),
        (node("b2", "balluff", update_order=950), ("A",)),
    ]
    infos = {"fw": online(), "b1": online("1.0.0"), "b2": online("1.0.0"), "plc": online("V4.5.2")}
    items = build_plan(devices, infos, CAPS, [pkg(), pkg("balluff", "1.6.1")], simulated=True)
    assert [i.entry_id for i in items] == ["b1", "plc", "fw", "b2"]
    assert [i.position for i in items] == [1, 2, 3, 4]


def test_release_and_integrity(firmware_dir):
    fw = FirmwareUpdater(firmware_dir)
    name = "Ads-tec-IRF3xxx-2.3.4-SVN-R1.B-1.bin"
    assert {p.name: p.status for p in fw.packages()}[name] == "unreleased"
    # Falsche Hersteller-Prüfsumme wird abgelehnt
    try:
        fw.release(name, version="2.3.4", models=[], vendor_sha256="0" * 64, released_by="t", notes=None)
        raise AssertionError("Freigabe hätte abgelehnt werden müssen")
    except Exception as exc:
        assert "Hersteller-Prüfsumme" in str(exc)
    sha = fw.hash_of(name)
    pkg_ = fw.release(name, version="2.3.4", models=["IRF3*"], vendor_sha256=sha, released_by="t", notes=None)
    assert pkg_.status == "released" and pkg_.vendor_checksum_verified
    # Manipulation der Datei → Freigabe ungültig
    (firmware_dir / name).write_bytes(b"MANIPULIERT")
    assert fw.package(name).status == "hash_mismatch"


def test_model_from_title_or_keepass_when_driver_cannot_read_it():
    restricted = [pkg(models=["IRF3*"])]
    no_model = online(model=None)
    # Eintragsname enthält das Modell
    n = DeviceNode(id="1", title="IRF3401 Zellenfirewall", serial_number="AX1", device_type="adstec", serial_status="ok")
    assert plan_item(n, (), no_model, CAPS["adstec"], restricted, simulated=False).status == "ready"
    # Falsches Modell im Namen wird nicht übernommen → nicht prüfbar → blockiert
    n = DeviceNode(id="2", title="IRF2210 Router", serial_number="AX2", device_type="adstec", serial_status="ok")
    assert plan_item(n, (), no_model, CAPS["adstec"], restricted, simulated=False).status == "blocked"
    # KeePass-Feld Model entscheidet allein, auch gegen den Namen
    n = DeviceNode(id="3", title="IRF3401 alt", serial_number="AX3", device_type="adstec", serial_status="ok", model="IRF2210")
    assert plan_item(n, (), no_model, CAPS["adstec"], restricted, simulated=False).status == "blocked"
    # Neutraler Name ohne Modell → blockiert mit Hinweis
    n = DeviceNode(id="4", title="Firewall Halle 1", serial_number="AX4", device_type="adstec", serial_status="ok")
    item = plan_item(n, (), no_model, CAPS["adstec"], restricted, simulated=False)
    assert item.status == "blocked" and any("Model" in b for b in item.blockers)
