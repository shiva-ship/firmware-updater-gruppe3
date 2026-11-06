"""Prüft die Übersetzung zwischen murrelektronik.py und der Adapter-Schnittstelle."""

import tempfile

import pytest
from fake_impact67 import PASSWORD, USERNAME, FakeImpact67
from test_murrelektronik import make_m3z

from backend.services.devices.base import CriticalDeviceError, DeviceError
from backend.services.devices.murrelektronik import MurrelektronikAdapter
from backend.services.keepass import DeviceAccess


class FastAdapter(MurrelektronikAdapter):
    def _driver(self, access, progress=None):
        driver = super()._driver(access, progress)
        driver.retry_delay = driver.reset_settle = driver.stable_delay = 0.01
        driver.poll_interval = 0.01
        driver.ready_timeout = 0.3
        return driver


def access_for(fake):
    return DeviceAccess("id", "IMPACT67", f"{fake.url}/", USERNAME, PASSWORD)


@pytest.fixture
def firmware():
    with tempfile.TemporaryDirectory() as folder:
        yield make_m3z(folder)


def test_read_info_maps_device_fields():
    with FakeImpact67() as fake:
        info = FastAdapter().read_info(access_for(fake))
    assert (info.connection, info.installed_version) == ("online", "V1.7.1")
    assert info.serial_number == "TEST-SERIAL-1"


def test_incomplete_keepass_entry_reports_error():
    info = FastAdapter().read_info(DeviceAccess("id", "IMPACT67", "http://127.0.0.1", "", ""))
    assert info.connection == "error"


def test_update_reports_progress_and_version(firmware):
    steps = []
    with FakeImpact67() as fake:
        result = FastAdapter().update(access_for(fake), firmware, "1.9.1", lambda s, f: steps.append(s))
    assert result.previous_version == "V1.7.1"
    assert result.details["installed_version"] == "V1.9.1"
    assert steps


def test_wrong_release_version_never_touches_the_device(firmware):
    with FakeImpact67() as fake:
        with pytest.raises(DeviceError):
            FastAdapter().update(access_for(fake), firmware, "1.7.1", lambda s, f: None)
        assert fake.upload_calls == 0


def test_stop_before_upload_is_a_device_error(firmware):
    with FakeImpact67(product_id="1") as fake:
        with pytest.raises(DeviceError):
            FastAdapter().update(access_for(fake), firmware, "1.9.1", lambda s, f: None)


def test_failure_after_upload_start_is_critical(firmware):
    with FakeImpact67() as fake:
        fake.never_returns = True
        with pytest.raises(CriticalDeviceError):
            FastAdapter().update(access_for(fake), firmware, "1.9.1", lambda s, f: None)
