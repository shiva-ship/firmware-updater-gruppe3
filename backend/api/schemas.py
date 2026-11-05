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


class EntryOut(BaseModel):
    id: str
    title: str
    serial_number: str | None
    # "field" = KeePass-Feld SerialNumber/Serialnummer/serial_number, "notes" = aus den Notizen erkannt
    serial_source: Literal["field", "notes"] | None = None


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


class TreeOut(BaseModel):
    database: DatabaseOut
    root: GroupOut
    stats: TreeStatsOut
