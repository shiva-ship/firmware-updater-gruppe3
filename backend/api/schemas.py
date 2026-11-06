"""Request-/Response-Modelle. Antworten enthalten nur Metadaten für die Oberfläche."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=1024)


class UserOut(BaseModel):
    id: int
    username: str
    role: str


class SessionOut(BaseModel):
    authenticated: bool
    user: UserOut | None = None
    csrf_token: str | None = None
    expires_at: datetime | None = None


class DatabaseOut(BaseModel):
    id: str
    filename: str
    size_bytes: int
    status: str
    uploaded_at: datetime
    unlocked_at: datetime | None = None


class DatabaseListOut(BaseModel):
    databases: list[DatabaseOut]
    max_upload_bytes: int
    max_databases: int


class UnlockRequest(StrictModel):
    master_password: SecretStr = Field(min_length=1, max_length=4096)


DeviceTypeLiteral = Literal["balluff", "adstec", "siemens"]


class EntryOut(BaseModel):
    id: str
    title: str
    serial_number: str | None
    # "field" = KeePass-Feld SerialNumber/Serialnummer/serial_number, "notes" = aus den Notizen erkannt
    serial_source: Literal["field", "notes"] | None = None
    # "duplicate"/"missing" ⇒ keine automatische Gerätezuordnung
    serial_status: Literal["ok", "missing", "duplicate"] = "missing"
    device_type: DeviceTypeLiteral | None = None
    host: str | None = None
    mac_address: str | None = None
    model: str | None = None
    update_order: int | None = None
    has_notes: bool = False


class GroupOut(BaseModel):
    id: str
    name: str
    entry_count: int
    total_entry_count: int
    entries: list[EntryOut]
    groups: list[GroupOut]


class TreeStatsOut(BaseModel):
    groups: int
    entries: int
    entries_without_serial: int
    serials_from_notes: int
    duplicate_serials: int


class TreeOut(BaseModel):
    database: DatabaseOut
    root: GroupOut
    stats: TreeStatsOut


class NotesOut(BaseModel):
    notes: str | None
    redacted: bool


class FirmwareFileOut(BaseModel):
    name: str
    size_bytes: int
    device_type: Literal["balluff", "adstec"]


class FirmwareFileListOut(BaseModel):
    files: list[FirmwareFileOut]


class FirmwarePackageOut(BaseModel):
    name: str
    size_bytes: int
    vendor: str
    sha256: str
    filename_version: str | None
    status: Literal["released", "unreleased", "hash_mismatch"]
    version: str | None
    models: list[str]
    vendor_checksum_verified: bool
    released_by: str | None
    released_at: str | None
    notes: str | None


class FirmwarePackageListOut(BaseModel):
    packages: list[FirmwarePackageOut]


class ReleaseRequest(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=64)
    models: list[str] = Field(default_factory=list, max_length=32)
    vendor_sha256: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=500)
    confirm: Literal[True]


class DriverOut(BaseModel):
    vendor: str
    label: str
    driver_module: str
    firmware_suffixes: list[str]
    supports_read: bool
    supports_update: bool
    driver_available: bool
    driver_error: str | None
    notes: str


class SystemOut(BaseModel):
    mode: Literal["demo", "live"]
    version: str
    drivers: list[DriverOut]


class DeviceStatusOut(BaseModel):
    connection: Literal["online", "offline", "error", "not_checked"]
    installed_version: str | None
    model: str | None
    serial_number: str | None
    mac_address: str | None
    message: str | None
    simulated: bool
    checked_at: datetime


class InventoryOut(BaseModel):
    mode: Literal["demo", "live"]
    devices: dict[str, DeviceStatusOut]


class PrepareRequest(StrictModel):
    entry_ids: list[str] = Field(min_length=1, max_length=500)
    # Nur im LIVE-Modus erforderlich (lesender Zugriff auf die Geräte).
    master_password: SecretStr | None = Field(default=None, max_length=4096)


class CheckOut(BaseModel):
    key: str
    label: str
    status: Literal["ok", "warn", "fail", "skip"]
    message: str


class PlanItemOut(BaseModel):
    position: int
    entry_id: str
    title: str
    path: list[str]
    vendor: str | None
    vendor_label: str
    serial_number: str | None
    serial_status: str
    host: str | None
    model: str | None
    installed_version: str | None
    target_version: str | None
    package: str | None
    driver_module: str | None
    status: Literal["ready", "up_to_date", "blocked", "no_driver"]
    checks: list[CheckOut]
    effects: list[str]
    order_reason: str
    simulated: bool
    warnings: list[str]
    blockers: list[str]


class PlanOut(BaseModel):
    id: str
    db_id: str
    mode: Literal["demo", "live"]
    simulated: bool
    created_at: datetime
    items: list[PlanItemOut]
    counts: dict[str, int]
    requires_stop_run: bool
    # LIVE: Zugangsdaten aus dem Vorbereiten liegen noch vor → Freigabe ohne erneute Passworteingabe
    credentials_ready: bool = False


class AuthorizeRequest(StrictModel):
    # Leer lassen, um die beim Vorbereiten gelesenen Zugangsdaten zu verwenden (LIVE).
    master_password: SecretStr | None = Field(default=None, max_length=4096)


class AuthorizeOut(BaseModel):
    authorization_id: str
    expires_in_seconds: int


class ExecuteRequest(StrictModel):
    authorization_id: str = Field(min_length=1, max_length=128)
    confirm: Literal[True]
    approve_plc_stop_run: bool = False


class JobLogOut(BaseModel):
    at: datetime
    level: str
    message: str


class JobItemOut(BaseModel):
    entry_id: str
    title: str
    vendor_label: str
    serial_number: str | None
    position: int
    plan_status: str
    from_version: str | None
    to_version: str | None
    package: str | None
    state: Literal["pending", "running", "succeeded", "dry_run_ok", "failed", "skipped", "aborted"]
    step: str | None
    progress: float
    message: str | None
    verified_version: str | None
    started_at: datetime | None
    finished_at: datetime | None
    log: list[JobLogOut]


class JobOut(BaseModel):
    id: str
    plan_id: str
    dry_run: bool
    simulated: bool
    state: Literal["running", "completed", "completed_with_errors", "aborted", "cancelled"]
    created_at: datetime
    finished_at: datetime | None
    abort_reason: str | None
    cancel_requested: bool
    summary: dict[str, int]
    items: list[JobItemOut]
