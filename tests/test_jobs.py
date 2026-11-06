"""Warteschlange und Fehlerbehandlung bei Sammelupdates."""

from __future__ import annotations

import threading

from backend.services.devices import CriticalDeviceError, DeviceError, DeviceInfo, UpdateResult
from backend.services.updates import JobRunner, new_job
from backend.services.updates.planner import PlanItem


def item(entry_id, status="ready", position=1):
    return PlanItem(
        entry_id=entry_id, title=entry_id, path=[], vendor="adstec", vendor_label="ads-tec", serial_number=entry_id,
        serial_status="ok", host=None, model=None, installed_version="2.3.1", target_version="2.3.4",
        package="p.bin", package_sha256="x", driver_module="firewall_update", status=status, checks=[], effects=[],
        order_key=1, order_reason="", simulated=True, position=position,
    )


class FakeExecutor:
    def __init__(self, failures=None, verify_version="2.3.4", bad_package=False):
        self.failures = failures or {}
        self.verify_version = verify_version
        self.bad_package = bad_package
        self.updated: list[str] = []
        self.order: list[str] = []

    def verify_package(self, it):
        if self.bad_package:
            raise CriticalDeviceError("SHA-256 geändert")

    def update(self, it, progress):
        self.order.append(it.entry_id)
        progress("Upload", 0.5)
        exc = self.failures.get(it.entry_id)
        if exc:
            raise exc
        self.updated.append(it.entry_id)
        return UpdateResult(previous_version="2.3.1", message="ok")

    def read_info(self, it):
        return DeviceInfo(connection="online", installed_version=self.verify_version)


def run(items, executor, dry_run=False, cancel=False):
    job = new_job("plan", items, owner_user_id=1, owner_session_id="s", dry_run=dry_run, simulated=True)
    job.cancel_requested = cancel
    JobRunner(job, executor, threading.Lock()).run()
    return job


def states(job):
    return {i.entry_id: i.state for i in job.items}


def test_sequential_success_and_verification():
    ex = FakeExecutor()
    job = run([item("a"), item("b")], ex)
    assert job.state == "completed"
    assert ex.order == ["a", "b"]
    assert states(job) == {"a": "succeeded", "b": "succeeded"}
    assert all(i.verified_version == "2.3.4" for i in job.items)


def test_non_critical_failure_continues():
    ex = FakeExecutor(failures={"a": DeviceError("Login fehlgeschlagen")})
    job = run([item("a"), item("b")], ex)
    assert job.state == "completed_with_errors"
    assert states(job) == {"a": "failed", "b": "succeeded"}


def test_critical_failure_stops_queue():
    ex = FakeExecutor(failures={"a": CriticalDeviceError("Upload abgebrochen")})
    job = run([item("a"), item("b"), item("c", status="no_driver")], ex)
    assert job.state == "aborted"
    assert states(job) == {"a": "failed", "b": "aborted", "c": "skipped"}
    assert ex.order == ["a"]


def test_unexpected_exception_is_treated_as_unknown_state():
    ex = FakeExecutor(failures={"a": ValueError("kaputt")})
    job = run([item("a"), item("b")], ex)
    assert job.state == "aborted" and states(job)["b"] == "aborted"


def test_failed_verification_is_critical():
    ex = FakeExecutor(verify_version="2.3.1")
    job = run([item("a"), item("b")], ex)
    assert job.state == "aborted"
    assert states(job) == {"a": "failed", "b": "aborted"}


def test_missing_driver_is_never_success():
    ex = FakeExecutor()
    job = run([item("a", status="no_driver"), item("b", status="blocked"), item("c", status="up_to_date")], ex)
    assert set(states(job).values()) == {"skipped"}
    assert ex.order == []
    assert job.summary()["succeeded"] == 0


def test_integrity_failure_stops_before_any_change():
    ex = FakeExecutor(bad_package=True)
    job = run([item("a"), item("b")], ex)
    assert job.state == "aborted" and ex.order == []


def test_dry_run_changes_nothing():
    ex = FakeExecutor()
    job = run([item("a"), item("b", status="no_driver")], ex, dry_run=True)
    assert job.state == "completed"
    assert states(job) == {"a": "dry_run_ok", "b": "skipped"}
    assert ex.order == []


def test_cancel_before_next_device():
    job = run([item("a"), item("b")], FakeExecutor(), cancel=True)
    assert job.state == "cancelled" and set(states(job).values()) == {"aborted"}
