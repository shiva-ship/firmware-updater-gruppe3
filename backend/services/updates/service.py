"""Orchestrierung: Inventar, Updatepläne, Freigaben und Aufträge.

Sicherheitsregeln:
* DEMO: Es wird nie ein Gerätetreiber aufgerufen; alle Geräteinformationen sind simuliert.
* LIVE: Geräte werden nur über die vorhandenen Treiber angesprochen.
* Ein echtes Update braucht (1) einen gültigen Plan, (2) eine Freigabe und (3) eine ausdrückliche
  Bestätigung. Die Freigabe erfordert das Masterpasswort – im LIVE-Modus genügt die Eingabe beim
  Vorbereiten: Die dabei gelesenen Zugangsdaten bleiben höchstens ``credential_ttl`` Sekunden am
  Plan und sind nur einmal verwendbar. Danach liegen sie nur für die Dauer des Auftrags im Speicher.
* Es läuft höchstens ein Auftrag gleichzeitig.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.errors import AppError
from backend.services.devices import (
    CriticalDeviceError,
    DemoSimulator,
    DeviceAdapter,
    DeviceError,
    DeviceInfo,
)
from backend.services.firmware import FirmwareUpdater
from backend.services.keepass import DeviceAccess, DeviceNode, KeePassSessionManager

from .jobs import Job, JobItem, JobRunner, new_job
from .planner import AdapterCapabilities, PlanItem, build_plan

logger = logging.getLogger(__name__)

MAX_PLAN_DEVICES = 500
READ_WORKERS = 4  # nur lesende Abfragen dürfen begrenzt parallel laufen


class PlanNotFound(AppError):
    status_code = 404
    code = "plan_not_found"
    message = "Der Updateplan existiert nicht mehr. Bitte bereiten Sie die Updates erneut vor."


class PlanOutdated(AppError):
    status_code = 409
    code = "plan_outdated"
    message = "Die Datenbank wurde seit der Planung aktualisiert. Bitte bereiten Sie die Updates erneut vor."


class NothingToUpdate(AppError):
    status_code = 409
    code = "nothing_to_update"
    message = "Der Plan enthält kein Gerät, das aktualisiert werden kann."


class JobBusy(AppError):
    status_code = 409
    code = "job_busy"
    message = "Es läuft bereits ein Update-Auftrag. Bitte warten Sie, bis er abgeschlossen ist."


class JobNotFound(AppError):
    status_code = 404
    code = "job_not_found"
    message = "Der Auftrag wurde nicht gefunden."


class AuthorizationInvalid(AppError):
    status_code = 403
    code = "authorization_invalid"
    message = "Die Freigabe ist abgelaufen oder ungültig. Bitte geben Sie das Masterpasswort erneut ein."


class InvalidSelection(AppError):
    status_code = 400
    code = "invalid_selection"
    message = "Die Auswahl enthält unbekannte Geräte."


class MasterPasswordRequired(AppError):
    status_code = 400
    code = "master_password_required"
    message = "Im LIVE-Modus wird zum Auslesen der Geräte das Masterpasswort benötigt."


class StopRunNotApproved(AppError):
    status_code = 400
    code = "stop_run_not_approved"
    message = "Der Plan enthält Geräte, die STOP/RUN erfordern. Dafür ist eine gesonderte Freigabe nötig."


@dataclass
class Plan:
    id: str
    db_id: str
    session_id: str
    user_id: int
    tree_version: datetime | None
    items: list[PlanItem]
    simulated: bool
    created_at: datetime
    expires_at: float
    # Beim Vorbereiten (LIVE) gelesene Zugangsdaten – einmalig für die Freigabe verwendbar.
    access: dict[str, DeviceAccess] = field(default_factory=dict, repr=False)
    access_expires_at: float = 0.0

    @property
    def ready_items(self) -> list[PlanItem]:
        return [i for i in self.items if i.status == "ready"]


@dataclass
class Authorization:
    id: str
    plan_id: str
    session_id: str
    expires_at: float
    access: dict[str, DeviceAccess] = field(default_factory=dict, repr=False)


class _DemoExecutor:
    def __init__(self, service: UpdateService, plan: Plan, nodes: dict[str, DeviceNode]):
        self.service, self.plan, self.nodes = service, plan, nodes

    def verify_package(self, item: JobItem) -> None:
        self.service._verify_package(item)

    def update(self, item, progress):
        return self.service.simulator.update(self.nodes[item.entry_id], None, item.to_version or "", progress)

    def read_info(self, item):
        info = self.service.simulator.read_info(self.nodes[item.entry_id])
        self.service._remember(self.plan.session_id, self.plan.db_id, item.entry_id, info)
        return info


class _LiveExecutor:
    def __init__(self, service: UpdateService, plan: Plan, nodes: dict[str, DeviceNode], access: dict[str, DeviceAccess]):
        self.service, self.plan, self.nodes, self.access = service, plan, nodes, access

    def _adapter(self, item: JobItem) -> DeviceAdapter:
        vendor = self.nodes[item.entry_id].device_type
        adapter = self.service.adapters.get(vendor or "")
        if adapter is None or not adapter.supports_update:
            raise DeviceError("Kein Firmware-Update-Treiber vorhanden.")
        return adapter

    def verify_package(self, item: JobItem) -> None:
        self.service._verify_package(item)

    def update(self, item, progress):
        access = self.access.get(item.entry_id)
        if access is None:
            raise DeviceError("Zugangsdaten nicht verfügbar.")
        adapter = self._adapter(item)
        # Unmittelbar vor der Änderung: Gerät erneut prüfen (Version und Seriennummer unverändert?)
        progress("Gerätezustand wird erneut geprüft", 0.02)
        before = adapter.read_info(access)
        node = self.nodes[item.entry_id]
        if before.connection != "online":
            raise DeviceError(before.message or "Gerät nicht erreichbar.")
        if before.installed_version != item.from_version:
            raise DeviceError(f"Installierte Version hat sich seit der Planung geändert ({before.installed_version}).")
        if before.serial_number and node.serial_number and before.serial_number.casefold() != node.serial_number.casefold():
            raise DeviceError("Seriennummer des Geräts stimmt nicht mit KeePass überein.")
        path = self.service.firmware.resolve_file(item.package or "", node.device_type or "")
        return adapter.update(access, path, item.to_version or "", progress)

    def read_info(self, item):
        info = self._adapter(item).read_info(self.access[item.entry_id])
        self.service._remember(self.plan.session_id, self.plan.db_id, item.entry_id, info)
        return info


class UpdateService:
    def __init__(
        self,
        *,
        mode: str,
        keepass: KeePassSessionManager,
        firmware: FirmwareUpdater,
        adapters: dict[str, DeviceAdapter],
        simulator: DemoSimulator,
        plan_ttl_seconds: int = 1800,
        authorization_ttl_seconds: int = 180,
        credential_ttl_seconds: int = 900,
        clock=time.monotonic,
    ) -> None:
        self.mode = mode
        self.keepass = keepass
        self.firmware = firmware
        self.adapters = adapters
        self.simulator = simulator
        self.plan_ttl = plan_ttl_seconds
        self.auth_ttl = authorization_ttl_seconds
        self.credential_ttl = credential_ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._job_lock = threading.Lock()  # schützt Zustandsänderungen laufender Aufträge
        self._inventory: dict[tuple[str, str], dict[str, DeviceInfo]] = {}
        self._plans: dict[str, Plan] = {}
        self._auths: dict[str, Authorization] = {}
        self._jobs: dict[str, Job] = {}
        self._active_job: str | None = None
        self._driver_status: dict[str, tuple[bool, str | None]] = {}

    @property
    def simulated(self) -> bool:
        return self.mode == "demo"

    # ------------------------------------------------------------------ Treiber
    def capabilities(self) -> dict[str, AdapterCapabilities]:
        caps = {}
        for vendor, adapter in self.adapters.items():
            if self.simulated:
                # Im DEMO-Modus werden Treiber nicht geladen; maßgeblich ist die deklarierte Unterstützung.
                available, error = True, None
            else:
                if vendor not in self._driver_status:
                    self._driver_status[vendor] = adapter.driver_available()
                available, error = self._driver_status[vendor]
            caps[vendor] = AdapterCapabilities(
                vendor=vendor,
                label=adapter.label,
                driver_module=adapter.driver_module,
                supports_update=adapter.supports_update,
                driver_available=available,
                driver_error=error,
                requires_stop_run=adapter.requires_stop_run and adapter.supports_update,
            )
        return caps

    def driver_overview(self) -> list[dict]:
        rows = []
        for vendor, adapter in self.adapters.items():
            available, error = adapter.driver_available()
            rows.append({
                "vendor": vendor,
                "label": adapter.label,
                "driver_module": adapter.driver_module,
                "firmware_suffixes": list(adapter.firmware_suffixes),
                "supports_read": adapter.supports_read,
                "supports_update": adapter.supports_update,
                "driver_available": available,
                "driver_error": error,
                "notes": adapter.notes,
            })
        return rows

    # ------------------------------------------------------------------ Inventar
    def _remember(self, session_id: str, db_id: str, entry_id: str, info: DeviceInfo) -> None:
        with self._lock:
            self._inventory.setdefault((session_id, db_id), {})[entry_id] = info

    def inventory(self, session_id: str, db_id: str) -> dict[str, DeviceInfo]:
        with self._lock:
            return dict(self._inventory.get((session_id, db_id), {}))

    def _resolve_nodes(self, db_id: str, session_id: str, user_id: int, entry_ids: list[str]):
        handle, root = self.keepass.get_tree(db_id, session_id, user_id)
        index = {e.id: (e, path) for e, path in root.iter_entries_with_path()}
        unique = list(dict.fromkeys(entry_ids))
        if not unique or len(unique) > MAX_PLAN_DEVICES or any(i not in index for i in unique):
            raise InvalidSelection()
        return handle, [index[i] for i in unique]

    def _read_live(self, nodes: list[DeviceNode], access: dict[str, DeviceAccess]) -> dict[str, DeviceInfo]:
        def read(node: DeviceNode) -> tuple[str, DeviceInfo]:
            adapter = self.adapters.get(node.device_type or "")
            if adapter is None or not adapter.supports_read:
                return node.id, DeviceInfo(connection="not_checked", message="Kein Treiber für diesen Gerätetyp.")
            acc = access.get(node.id)
            if acc is None:
                return node.id, DeviceInfo(connection="error", message="Eintrag nicht in der KeePass-Datei gefunden.")
            try:
                return node.id, adapter.read_info(acc)
            except Exception as exc:
                return node.id, DeviceInfo(connection="error", message=f"{type(exc).__name__}: {exc}"[:300])

        with ThreadPoolExecutor(max_workers=READ_WORKERS) as pool:
            return dict(pool.map(read, nodes))

    # ------------------------------------------------------------------ Planung
    def prepare(self, db_id: str, session_id: str, user_id: int, entry_ids: list[str], master_password: str | None) -> Plan:
        handle, devices = self._resolve_nodes(db_id, session_id, user_id, entry_ids)
        nodes = [n for n, _ in devices]
        access: dict[str, DeviceAccess] = {}
        if self.simulated:
            infos = {n.id: self.simulator.read_info(n) for n in nodes}
        else:
            if master_password:
                access = self.keepass.read_device_access(db_id, session_id, user_id, master_password, [n.id for n in nodes])
            else:
                # Login-Daten aus dem Entsperren ("Daten aktualisieren") verwenden, solange gültig
                cached = self.keepass.cached_access(db_id, session_id, user_id, [n.id for n in nodes])
                if cached is None:
                    raise MasterPasswordRequired("Bitte geben Sie das Masterpasswort erneut ein.")
                access = cached
            infos = self._read_live(nodes, access)
        for entry_id, info in infos.items():
            self._remember(session_id, db_id, entry_id, info)

        items = build_plan(devices, infos, self.capabilities(), self.firmware.packages(), simulated=self.simulated)
        plan = Plan(
            id=secrets.token_hex(16),
            db_id=db_id,
            session_id=session_id,
            user_id=user_id,
            tree_version=handle.unlocked_at,
            items=items,
            simulated=self.simulated,
            created_at=datetime.now(timezone.utc),
            expires_at=self._clock() + self.plan_ttl,
        )
        ready_ids = {i.entry_id for i in plan.ready_items}
        if ready_ids and access:
            # Nur die Zugangsdaten der aktualisierbaren Geräte behalten, alle anderen sofort verwerfen.
            plan.access = {k: v for k, v in access.items() if k in ready_ids}
            plan.access_expires_at = self._clock() + self.credential_ttl
        del access
        with self._lock:
            self._purge()
            self._plans[plan.id] = plan
        logger.info("Updateplan erstellt: %d Gerät(e), %d bereit", len(items), len(plan.ready_items))
        return plan

    def get_plan(self, plan_id: str, session_id: str, user_id: int) -> Plan:
        with self._lock:
            self._purge()
            plan = self._plans.get(plan_id)
        if plan is None or plan.session_id != session_id or plan.user_id != user_id:
            raise PlanNotFound()
        handle = self.keepass.get(plan.db_id, session_id, user_id)
        if handle.unlocked_at != plan.tree_version:
            raise PlanOutdated()
        return plan

    def _nodes_for(self, plan: Plan) -> dict[str, DeviceNode]:
        _, root = self.keepass.get_tree(plan.db_id, plan.session_id, plan.user_id)
        return {e.id: e for e, _ in root.iter_entries_with_path() if any(i.entry_id == e.id for i in plan.items)}

    def _verify_package(self, item: JobItem) -> None:
        pkg = self.firmware.package(item.package or "")
        if pkg is None or pkg.status != "released":
            raise CriticalDeviceError("Firmwarepaket ist nicht (mehr) freigegeben.")
        if self.firmware.hash_of(pkg.name, fresh=True) != item.package_sha256:
            raise CriticalDeviceError("SHA-256 des Firmwarepakets hat sich seit der Planung geändert.")
        if pkg.version != item.to_version:
            raise CriticalDeviceError("Zielversion der Freigabe hat sich seit der Planung geändert.")

    # ------------------------------------------------------------------ Aufträge
    def _start(self, plan: Plan, *, dry_run: bool, executor) -> Job:
        job = new_job(plan.id, plan.items, owner_user_id=plan.user_id, owner_session_id=plan.session_id,
                      dry_run=dry_run, simulated=plan.simulated)
        with self._lock:
            if self._active_job is not None:
                raise JobBusy()
            self._active_job = job.id
            self._jobs[job.id] = job

        def done(_job: Job) -> None:
            with self._lock:
                if self._active_job == _job.id:
                    self._active_job = None
            logger.info("Auftrag %s beendet: %s %s", _job.id, _job.state, _job.summary())

        runner = JobRunner(job, executor, self._job_lock, on_done=done)
        threading.Thread(target=runner.run, name=f"update-job-{job.id[:8]}", daemon=True).start()
        return job

    def start_dry_run(self, plan_id: str, session_id: str, user_id: int) -> Job:
        plan = self.get_plan(plan_id, session_id, user_id)
        if not plan.ready_items:
            raise NothingToUpdate()
        return self._start(plan, dry_run=True, executor=_DemoExecutor(self, plan, self._nodes_for(plan)))

    def credentials_ready(self, plan: Plan) -> bool:
        return bool(plan.access) and plan.access_expires_at > self._clock()

    def authorize(self, plan_id: str, session_id: str, user_id: int, master_password: str | None) -> Authorization:
        plan = self.get_plan(plan_id, session_id, user_id)
        if not plan.ready_items:
            raise NothingToUpdate()
        if master_password is None:
            # Zugangsdaten aus dem Vorbereiten weiterverwenden – nur einmal und nur innerhalb der Frist.
            with self._lock:
                ready = self.credentials_ready(plan)
                access, plan.access = (plan.access if ready else {}), {}
            if not ready:
                # Fallback: Zwischenspeicher aus dem Entsperren
                cached = self.keepass.cached_access(plan.db_id, session_id, user_id, [i.entry_id for i in plan.ready_items])
                if not self.simulated and not cached:
                    raise MasterPasswordRequired("Bitte geben Sie das Masterpasswort erneut ein.")
                if self.simulated and cached is None:
                    raise MasterPasswordRequired("Bitte geben Sie das Masterpasswort erneut ein.")
                access = cached or {}
        # Prüft das Masterpasswort serverseitig; im LIVE-Modus werden zugleich die Zugangsdaten gelesen.
        elif self.simulated:
            self.keepass.verify_master_password(plan.db_id, session_id, user_id, master_password)
            access: dict[str, DeviceAccess] = {}
        else:
            access = self.keepass.read_device_access(
                plan.db_id, session_id, user_id, master_password, [i.entry_id for i in plan.ready_items]
            )
        auth = Authorization(
            id=secrets.token_urlsafe(24),
            plan_id=plan.id,
            session_id=session_id,
            expires_at=self._clock() + self.auth_ttl,
            access=access,
        )
        with self._lock:
            self._purge()
            # Pro Plan gilt nur die jüngste Freigabe.
            for key in [k for k, a in self._auths.items() if a.plan_id == plan.id]:
                del self._auths[key]
            self._auths[auth.id] = auth
        return auth

    def execute(self, plan_id: str, session_id: str, user_id: int, authorization_id: str, approve_stop_run: bool) -> Job:
        plan = self.get_plan(plan_id, session_id, user_id)
        with self._lock:
            self._purge()
            auth = self._auths.pop(authorization_id, None)  # nur einmal verwendbar
        if auth is None or auth.plan_id != plan.id or auth.session_id != session_id:
            raise AuthorizationInvalid()
        if not plan.ready_items:
            raise NothingToUpdate()
        caps = self.capabilities()
        if any(caps.get(i.vendor or "") and caps[i.vendor or ""].requires_stop_run for i in plan.ready_items) and not approve_stop_run:
            raise StopRunNotApproved()
        nodes = self._nodes_for(plan)
        executor = _DemoExecutor(self, plan, nodes) if self.simulated else _LiveExecutor(self, plan, nodes, auth.access)
        job = self._start(plan, dry_run=False, executor=executor)
        logger.info("Firmwareupdate freigegeben: Auftrag %s, %d Gerät(e), Modus %s", job.id, len(plan.ready_items), self.mode)
        return job

    def get_job(self, job_id: str, user_id: int) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None or job.owner_user_id != user_id:
            raise JobNotFound()
        return job

    def cancel_job(self, job_id: str, user_id: int) -> Job:
        job = self.get_job(job_id, user_id)
        with self._job_lock:
            job.cancel_requested = True  # wirkt vor dem nächsten Gerät; ein laufendes Update wird nie unterbrochen
        return job

    def snapshot(self, job: Job):
        with self._job_lock:
            return job_to_dict(job)

    # ------------------------------------------------------------------ Aufräumen
    def _purge(self) -> None:
        now = self._clock()
        self.keepass.purge_expired_access()
        for key in [k for k, p in self._plans.items() if p.expires_at <= now]:
            del self._plans[key]
        for p in self._plans.values():
            if p.access and p.access_expires_at <= now:
                p.access = {}
        for key in [k for k, a in self._auths.items() if a.expires_at <= now]:
            del self._auths[key]

    def forget_session(self, session_id: str) -> None:
        with self._lock:
            for key in [k for k in self._inventory if k[0] == session_id]:
                del self._inventory[key]
            for key in [k for k, p in self._plans.items() if p.session_id == session_id]:
                del self._plans[key]
            for key in [k for k, a in self._auths.items() if a.session_id == session_id]:
                del self._auths[key]

    def forget_database(self, session_id: str, db_id: str) -> None:
        with self._lock:
            self._inventory.pop((session_id, db_id), None)
            for key in [k for k, p in self._plans.items() if p.db_id == db_id]:
                del self._plans[key]


def job_to_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "plan_id": job.plan_id,
        "dry_run": job.dry_run,
        "simulated": job.simulated,
        "state": job.state,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "abort_reason": job.abort_reason,
        "cancel_requested": job.cancel_requested,
        "summary": job.summary(),
        "items": [
            {
                "entry_id": i.entry_id,
                "title": i.title,
                "vendor_label": i.vendor_label,
                "serial_number": i.serial_number,
                "position": i.position,
                "plan_status": i.plan_status,
                "from_version": i.from_version,
                "to_version": i.to_version,
                "package": i.package,
                "state": i.state,
                "step": i.step,
                "progress": round(i.progress, 3),
                "message": i.message,
                "verified_version": i.verified_version,
                "started_at": i.started_at,
                "finished_at": i.finished_at,
                "log": [{"at": l.at, "level": l.level, "message": l.message} for l in i.log],
            }
            for i in job.items
        ],
    }
