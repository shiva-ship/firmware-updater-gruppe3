"""Kontrollierte, sequenzielle Ausführung eines Updateplans.

* Geräte werden strikt nacheinander in Planreihenfolge bearbeitet – nie parallel.
* ``DeviceError`` (Gerät nachweislich unverändert): Gerät gilt als fehlgeschlagen, die
  Warteschlange läuft weiter.
* ``CriticalDeviceError``, Integritätsfehler oder unerwartete Ausnahmen (unbekannter Zustand):
  Der gesamte Ablauf stoppt, alle folgenden Geräte werden nicht ausgeführt.
* Nach jedem Update wird die installierte Firmware erneut ausgelesen und verifiziert.
* Ein Gerät ohne Treiber ist nie „erfolgreich“, sondern „übersprungen“.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Protocol

from backend.services.devices import CriticalDeviceError, DeviceError, DeviceInfo, UpdateResult, compare_versions

from .planner import PlanItem

logger = logging.getLogger(__name__)

ItemState = Literal["pending", "running", "succeeded", "dry_run_ok", "failed", "skipped", "aborted"]
JobState = Literal["running", "completed", "completed_with_errors", "aborted", "cancelled"]

MAX_LOG_LINES = 200


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class LogLine:
    at: datetime
    level: Literal["info", "warn", "error"]
    message: str


@dataclass
class JobItem:
    entry_id: str
    title: str
    vendor_label: str
    serial_number: str | None
    position: int
    plan_status: str
    from_version: str | None
    to_version: str | None
    package: str | None
    package_sha256: str | None
    state: ItemState = "pending"
    step: str | None = None
    progress: float = 0.0
    message: str | None = None
    verified_version: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    log: list[LogLine] = field(default_factory=list)

    def add_log(self, level: Literal["info", "warn", "error"], message: str) -> None:
        if len(self.log) < MAX_LOG_LINES:
            self.log.append(LogLine(_now(), level, message))


@dataclass
class Job:
    id: str
    plan_id: str
    owner_user_id: int
    owner_session_id: str
    dry_run: bool
    simulated: bool
    items: list[JobItem]
    state: JobState = "running"
    created_at: datetime = field(default_factory=_now)
    finished_at: datetime | None = None
    abort_reason: str | None = None
    cancel_requested: bool = False

    def summary(self) -> dict[str, int]:
        counts = {k: 0 for k in ("pending", "running", "succeeded", "dry_run_ok", "failed", "skipped", "aborted")}
        for item in self.items:
            counts[item.state] += 1
        return counts


class Executor(Protocol):
    def verify_package(self, item: JobItem) -> None:
        """Wirft ``CriticalDeviceError``, wenn das Paket nicht mehr der Freigabe entspricht."""

    def update(self, item: JobItem, progress: Callable[[str, float], None]) -> UpdateResult: ...

    def read_info(self, item: JobItem) -> DeviceInfo: ...


class JobRunner:
    """Führt genau einen Job aus. Zustandsänderungen erfolgen unter ``lock`` (für Snapshots der API)."""

    def __init__(self, job: Job, executor: Executor, lock: threading.Lock, on_done: Callable[[Job], None] | None = None):
        self.job = job
        self.executor = executor
        self.lock = lock
        self.on_done = on_done

    def _set(self, item: JobItem, **changes) -> None:
        with self.lock:
            for key, value in changes.items():
                setattr(item, key, value)

    def _log(self, item: JobItem, level, message: str) -> None:
        with self.lock:
            item.add_log(level, message)

    def run(self) -> None:
        job = self.job
        try:
            for index, item in enumerate(job.items):
                if item.plan_status != "ready":
                    reason = {
                        "no_driver": "Kein Firmware-Update-Treiber – nicht ausgeführt.",
                        "up_to_date": "Bereits auf der Zielversion – nicht ausgeführt.",
                    }.get(item.plan_status, "Im Plan blockiert – nicht ausgeführt.")
                    self._set(item, state="skipped", message=reason, finished_at=_now())
                    continue
                if job.cancel_requested:
                    self._stop_remaining(index, "Vom Benutzer abgebrochen – nicht ausgeführt.")
                    with self.lock:
                        job.state = "cancelled"
                    return
                if not self._run_item(item):
                    self._stop_remaining(index + 1, "Ablauf nach sicherheitskritischem Fehler gestoppt – nicht ausgeführt.")
                    with self.lock:
                        job.state = "aborted"
                        job.abort_reason = f"{item.title}: {item.message}"
                    return
            with self.lock:
                job.state = "completed_with_errors" if any(i.state == "failed" for i in job.items) else "completed"
        except Exception:  # pragma: no cover – Schutznetz
            logger.exception("Unerwarteter Fehler im Update-Auftrag")
            with self.lock:
                job.state = "aborted"
                job.abort_reason = "Interner Fehler – Ablauf gestoppt."
        finally:
            with self.lock:
                job.finished_at = _now()
            if self.on_done:
                self.on_done(job)

    def _stop_remaining(self, start: int, message: str) -> None:
        with self.lock:
            for item in self.job.items[start:]:
                if item.state == "pending":
                    item.state = "aborted" if item.plan_status == "ready" else "skipped"
                    item.message = message if item.plan_status == "ready" else (item.message or "Nicht ausgeführt.")
                    item.finished_at = _now()

    def _run_item(self, item: JobItem) -> bool:
        """Gibt False zurück, wenn der gesamte Ablauf gestoppt werden muss."""
        self._set(item, state="running", started_at=_now(), progress=0.0, step="Paketintegrität wird geprüft")
        self._log(item, "info", "Start")
        try:
            self.executor.verify_package(item)
            self._log(item, "info", "SHA-256 des Firmwarepakets entspricht der Freigabe.")
            if self.job.dry_run:
                return self._dry_run_item(item)

            def progress(step: str, fraction: float) -> None:
                self._set(item, step=step, progress=max(0.0, min(fraction, 0.95)))
                self._log(item, "info", step)

            result = self.executor.update(item, progress)
            self._log(item, "info", result.message)

            self._set(item, step="Firmware wird erneut ausgelesen", progress=0.97)
            info = self.executor.read_info(item)
            if info.connection != "online" or compare_versions(info.installed_version, item.to_version) != 0:
                raise CriticalDeviceError(
                    f"Abschließende Verifikation fehlgeschlagen (gemeldet: {info.installed_version or 'keine Version'}, "
                    f"erwartet: {item.to_version})."
                )
            self._set(item, state="succeeded", progress=1.0, step=None, verified_version=info.installed_version,
                      message=f"Verifiziert: {info.installed_version}" + (" (simuliert)" if self.job.simulated else ""),
                      finished_at=_now())
            self._log(item, "info", f"Verifiziert: installierte Firmware {info.installed_version}")
            return True
        except DeviceError as exc:
            self._fail(item, str(exc), critical=False)
            return True
        except CriticalDeviceError as exc:
            self._fail(item, str(exc), critical=True)
            return False
        except Exception as exc:
            self._fail(item, f"Unerwarteter Fehler ({type(exc).__name__}) – Zustand unbekannt.", critical=True)
            return False

    def _dry_run_item(self, item: JobItem) -> bool:
        steps = [
            "Kompatibilität und Version laut Plan geprüft",
            f"Würde {item.package} übertragen ({item.from_version} → {item.to_version})",
            "Würde Neustart abwarten und Firmware verifizieren",
        ]
        for n, step in enumerate(steps, start=1):
            self._set(item, step=step, progress=n / (len(steps) + 1))
            self._log(item, "info", f"Dry-Run: {step}")
        self._set(item, state="dry_run_ok", progress=1.0, step=None, finished_at=_now(),
                  message="Dry-Run erfolgreich – am Gerät wurde nichts verändert.")
        return True

    def _fail(self, item: JobItem, message: str, *, critical: bool) -> None:
        self._set(item, state="failed", step=None, finished_at=_now(),
                  message=("Sicherheitskritisch: " if critical else "") + message)
        self._log(item, "error", message)
        logger.warning("Update %s für Eintrag %s fehlgeschlagen%s", self.job.id, item.entry_id,
                       " (kritisch)" if critical else "")


def new_job(plan_id: str, items: list[PlanItem], *, owner_user_id: int, owner_session_id: str,
            dry_run: bool, simulated: bool) -> Job:
    return Job(
        id=uuid.uuid4().hex,
        plan_id=plan_id,
        owner_user_id=owner_user_id,
        owner_session_id=owner_session_id,
        dry_run=dry_run,
        simulated=simulated,
        items=[
            JobItem(
                entry_id=i.entry_id,
                title=i.title,
                vendor_label=i.vendor_label,
                serial_number=i.serial_number,
                position=i.position,
                plan_status=i.status,
                from_version=i.installed_version,
                to_version=i.target_version,
                package=i.package,
                package_sha256=i.package_sha256,
            )
            for i in items
        ],
    )
