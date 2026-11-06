"""Run with: python3 -m unittest discover -s tests"""

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_impact67 import PASSWORD, USERNAME, FakeImpact67  # noqa: E402
from murrelektronik import FirmwareRejected, Impact67Driver, parse_version, read_package  # noqa: E402

PAYLOAD = b"firmware-bytes" * 100


def make_m3z(folder, version="1.09.01-V-00", article="54630", device_id="0x012A", bad_crc=False, omit=None):
    device = {
        "articleNo": article,
        "deviceDescription": "IMPACT67 Pro PNIO DIO8 IOL8 5P",
        "releaseVersion": version,
        "deviceId": device_id,
        "vendorId": "0x012F",
        "hwVersion": "2.00",
    }
    device.pop(omit, None)
    crc = zlib.crc32(PAYLOAD) ^ (1 if bad_crc else 0)
    info = {
        "device": device,
        "files": [{"name": "FWUPDATE.ZIP", "sizeInBytes": hex(len(PAYLOAD)), "crc32": hex(crc)}],
    }
    path = Path(folder) / f"{article}_{version}.m3z"
    with zipfile.ZipFile(path, "w") as container:
        container.writestr("info.json", json.dumps(info))
        container.writestr(f"Binaries/0x012F_{device_id}_{article}_2.00/FWUPDATE.ZIP", PAYLOAD)
    return str(path)


def make_driver(fake, **overrides):
    settings = {
        "host": fake.url,
        "username": USERNAME,
        "password": PASSWORD,
        "retries": 3,
        "retry_delay": 0.01,
        "reset_settle": 0.01,
        "poll_interval": 0.01,
        "ready_timeout": 1.0,
        "stable_delay": 0.01,
    }
    settings.update(overrides)
    return Impact67Driver(**settings)


class VersionTests(unittest.TestCase):
    def test_both_formats_compare_equal(self):
        self.assertEqual(parse_version("V1.9.1"), parse_version("1.09.01-V-00"))


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def test_reads_inner_firmware(self):
        package = read_package(make_m3z(self.folder.name))
        self.assertEqual(package.payload, PAYLOAD)
        self.assertEqual((package.vendor_id, package.device_id), (303, 298))

    def test_rejects_bad_crc(self):
        with self.assertRaises(FirmwareRejected):
            read_package(make_m3z(self.folder.name, bad_crc=True))

    def test_rejects_wrong_article(self):
        with self.assertRaises(FirmwareRejected):
            read_package(make_m3z(self.folder.name, article="54620"))

    def test_rejects_wrong_file_type(self):
        path = Path(self.folder.name) / "firmware.zip"
        path.write_bytes(b"x")
        with self.assertRaises(FirmwareRejected):
            read_package(str(path))

    def test_rejects_container_without_version(self):
        with self.assertRaises(FirmwareRejected):
            read_package(make_m3z(self.folder.name, omit="releaseVersion"))

    def test_rejects_hash_mismatch(self):
        path = Path(make_m3z(self.folder.name))
        path.with_suffix(".md5").write_text(f"SHA256 {hashlib.sha256(b'other').hexdigest()}")
        with self.assertRaises(FirmwareRejected):
            read_package(str(path))


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.firmware = make_m3z(self.folder.name)

    def test_get_info(self):
        with FakeImpact67() as fake:
            status = make_driver(fake).get_status()
        self.assertEqual(status["firmware"], "V1.7.1")
        self.assertEqual(status["name"], "IMPACT67 Pro PN DIO8 IOL8")
        self.assertEqual(status["mac"], "00:00:00:00:00:01")
        self.assertEqual(status["serial"], "TEST-SERIAL-1")
        self.assertEqual(status["state"], "online")

    def test_url_from_keepass_with_trailing_slash(self):
        with FakeImpact67() as fake:
            driver = make_driver(fake, host=f"{fake.url}/")
            self.assertEqual(driver.get_status()["state"], "online")

    def test_get_info_survives_sporadic_timeouts(self):
        with FakeImpact67() as fake:
            fake.flaky_reads = 2
            self.assertEqual(make_driver(fake).get_status()["state"], "online")

    def test_get_info_reports_offline(self):
        with FakeImpact67() as fake:
            fake.flaky_reads = 10
            self.assertEqual(make_driver(fake).get_status()["state"], "offline")

    def test_get_info_reports_error_when_rest_is_rejected(self):
        with FakeImpact67() as fake:
            fake.identification_status = 403
            self.assertEqual(make_driver(fake).get_status()["state"], "error")

    def test_full_update(self):
        with FakeImpact67() as fake:
            result = make_driver(fake).update(self.firmware)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(fake.uploaded, PAYLOAD)
            self.assertEqual(fake.firmware, "V1.9.1")

    def test_progress_reaches_the_caller(self):
        steps = []
        with FakeImpact67() as fake:
            make_driver(fake, progress=lambda message, fraction: steps.append(fraction)).update(self.firmware)
        self.assertEqual(steps, sorted(steps))
        self.assertGreater(len(steps), 5)

    def test_same_version_is_skipped(self):
        with FakeImpact67(firmware="V1.9.1") as fake:
            result = make_driver(fake).update(self.firmware)
            self.assertEqual(result["status"], "already_up_to_date")
            self.assertEqual(result["version"], "V1.9.1")
            self.assertEqual(fake.upload_calls, 0)

    def test_downgrade_is_blocked_by_default(self):
        older = make_m3z(self.folder.name, version="1.07.01-V-00")
        with FakeImpact67(firmware="V1.9.1") as fake:
            result = make_driver(fake).update(older)
            self.assertEqual((result["status"], result["phase"]), ("rejected", "precheck"))
            self.assertEqual(fake.upload_calls, 0)

    def test_broken_container_returns_a_result(self):
        broken = make_m3z(self.folder.name, omit="releaseVersion")
        with FakeImpact67() as fake:
            result = make_driver(fake).update(broken)
            self.assertEqual((result["status"], result["phase"]), ("rejected", "precheck"))

    def test_device_without_version_is_never_flashed(self):
        with FakeImpact67(firmware="") as fake:
            result = make_driver(fake).update(self.firmware)
            self.assertEqual((result["status"], result["phase"]), ("rejected", "precheck"))
            self.assertEqual(fake.upload_calls, 0)

    def test_temporary_device_error_is_not_a_rejection(self):
        with FakeImpact67() as fake:
            fake.identification_status = 503
            result = make_driver(fake).update(self.firmware)
            self.assertEqual((result["status"], result["phase"]), ("network_failed", "precheck"))

    def test_missing_version_after_flash_fails_verification(self):
        with FakeImpact67(new_firmware="") as fake:
            result = make_driver(fake, ready_timeout=0.2).update(self.firmware)
            self.assertEqual((result["status"], result["phase"]), ("failed", "verify"))

    def test_downgrade_can_be_allowed(self):
        older = make_m3z(self.folder.name, version="1.07.01-V-00")
        with FakeImpact67(firmware="V1.9.1", new_firmware="V1.7.1") as fake:
            result = make_driver(fake, allow_downgrade=True).update(older)
            self.assertEqual(result["status"], "ok")

    def test_wrong_product_never_uploads(self):
        with FakeImpact67(product_id="1") as fake:
            result = make_driver(fake).update(self.firmware)
            self.assertEqual(result["status"], "rejected")
            self.assertEqual(fake.upload_calls, 0)

    def test_wrong_password_is_tried_once(self):
        with FakeImpact67() as fake:
            result = make_driver(fake, password="wrong").update(self.firmware)
            self.assertEqual(result["status"], "rejected")
            self.assertEqual(fake.login_calls, 1)
            self.assertEqual(fake.upload_calls, 0)

    def test_password_never_appears_in_result(self):
        with FakeImpact67() as fake:
            fake.upload_status = 500
            result = make_driver(fake).update(self.firmware)
        self.assertNotIn(PASSWORD, json.dumps(result))

    def test_upload_error_does_not_reset(self):
        with FakeImpact67() as fake:
            fake.upload_status = 500
            result = make_driver(fake).update(self.firmware)
            self.assertEqual((result["status"], result["phase"]), ("failed", "upload"))
            self.assertEqual(fake.reset_calls, 0)

    def test_interrupted_upload_stops_without_retry(self):
        with FakeImpact67() as fake:
            fake.drop_upload = True
            result = make_driver(fake).update(self.firmware)
            self.assertEqual((result["status"], result["phase"]), ("network_failed", "upload"))
            self.assertEqual(fake.upload_calls, 1)
            self.assertEqual(fake.reset_calls, 0)

    def test_reset_connection_drop_still_verifies_version(self):
        with FakeImpact67() as fake:
            fake.drop_reset = True
            result = make_driver(fake).update(self.firmware)
            self.assertEqual(result["status"], "ok")

    def test_upload_time_is_not_limited_by_a_connect_timeout(self):
        with FakeImpact67() as fake:
            driver = make_driver(fake, upload_timeout=600.0)
            real_post = requests.post
            seen = []

            def recording_post(url, **kwargs):
                if url.endswith("/netx/firmware"):
                    seen.append(kwargs["timeout"])
                return real_post(url, **kwargs)

            with mock.patch("murrelektronik.requests.post", recording_post):
                driver.update(self.firmware)
        self.assertEqual(seen, [600.0])

    def test_unstable_device_is_never_flashed(self):
        with FakeImpact67() as fake:
            fake.fail_reads = {3}
            result = make_driver(fake).update(self.firmware)
            self.assertEqual(result["status"], "network_failed")
            self.assertEqual(fake.upload_calls, 0)
            self.assertEqual(fake.reset_calls, 0)

    def test_failed_reset_answer_still_checks_version(self):
        with FakeImpact67() as fake:
            fake.reset_status = 500
            fake.flash_on_failed_reset = True
            result = make_driver(fake).update(self.firmware)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["reset"], "HTTP 500")

    def test_failed_reset_without_flash_reports_old_version(self):
        with FakeImpact67() as fake:
            fake.reset_status = 500
            result = make_driver(fake, ready_timeout=0.2).update(self.firmware)
            self.assertEqual((result["status"], result["phase"]), ("failed", "verify"))
            self.assertIn("HTTP 500", result["detail"])

    def test_device_never_returns(self):
        with FakeImpact67() as fake:
            fake.never_returns = True
            result = make_driver(fake, ready_timeout=0.2).update(self.firmware)
            self.assertEqual((result["status"], result["phase"]), ("network_failed", "wait_ready"))

    def test_device_returns_with_old_version(self):
        with FakeImpact67() as fake:
            fake.flash_changes_version = False
            result = make_driver(fake).update(self.firmware)
            self.assertEqual((result["status"], result["phase"]), ("failed", "verify"))


if __name__ == "__main__":
    unittest.main()
