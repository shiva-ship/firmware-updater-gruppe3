"""Lokale Firmwarepakete im Ordner ``Firmware`` und ihre Freigabe.

Ein Paket darf nur installiert werden, wenn es in ``Firmware/firmware-manifest.json``
freigegeben ist und die SHA-256-Prüfsumme der Datei noch mit der Freigabe übereinstimmt.
Die Freigabe enthält Hersteller, Zielversion und die kompatiblen Modelle; optional die
Prüfsumme aus der Herstellerfreigabe, die beim Freigeben mit der Datei verglichen wird.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from backend.errors import AppError, FirmwareFileNotFound
from backend.services.devices.versions import parse_version, version_from_filename

logger = logging.getLogger(__name__)

FIRMWARE_SUFFIXES = {".bff": "balluff", ".bin": "adstec"}
_HEX = set("0123456789abcdef")

ReleaseStatus = Literal["released", "unreleased", "hash_mismatch"]


class InvalidRelease(AppError):
    status_code = 400
    code = "invalid_release"
    message = "Die Freigabe ist ungültig."


@dataclass(frozen=True)
class FirmwareFile:
    name: str
    size_bytes: int
    device_type: str


@dataclass
class FirmwarePackage:
    name: str
    size_bytes: int
    vendor: str
    sha256: str
    filename_version: str | None
    status: ReleaseStatus
    version: str | None = None
    models: list[str] = field(default_factory=list)
    vendor_checksum_verified: bool = False
    stop_run_tested: bool = False
    released_by: str | None = None
    released_at: str | None = None
    notes: str | None = None

    def model_compatible(self, model: str | None) -> bool | None:
        """True/False – Modell passt/passt nicht; None – nicht prüfbar (Modell unbekannt).
        Eine leere Modellliste bedeutet: freigegeben für alle Modelle dieses Herstellers."""
        if not self.models:
            return True
        if not model:
            return None
        return any(fnmatch.fnmatchcase(model.casefold(), p.casefold()) for p in self.models)


def list_firmware_files(firmware_dir: Path) -> list[FirmwareFile]:
    if not firmware_dir.is_dir():
        return []
    files = []
    for path in sorted(firmware_dir.iterdir()):
        device_type = FIRMWARE_SUFFIXES.get(path.suffix.lower())
        if device_type and path.is_file():
            files.append(FirmwareFile(path.name, path.stat().st_size, device_type))
    return files


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FirmwareUpdater:
    """Paketverwaltung (Name historisch, die Installation übernimmt der Update-Dienst)."""

    def __init__(self, firmware_dir: Path, manifest_path: Path | None = None) -> None:
        self.firmware_dir = firmware_dir
        self.manifest_path = manifest_path or firmware_dir / "firmware-manifest.json"
        self._hash_cache: dict[tuple[str, int, int], str] = {}
        self._lock = threading.Lock()

    def list_files(self) -> list[FirmwareFile]:
        return list_firmware_files(self.firmware_dir)

    def resolve_file(self, name: str, device_type: str) -> Path:
        # Nur Namen aus der eigenen Liste zulassen, nie einen Pfad aus der Anfrage.
        for file in self.list_files():
            if file.name == name and file.device_type == device_type:
                return self.firmware_dir / file.name
        raise FirmwareFileNotFound()

    def hash_of(self, name: str, *, fresh: bool = False) -> str:
        path = self.firmware_dir / name
        st = path.stat()
        key = (name, st.st_size, st.st_mtime_ns)
        with self._lock:
            cached = None if fresh else self._hash_cache.get(key)
        if cached:
            return cached
        value = sha256_file(path)
        with self._lock:
            self._hash_cache[key] = value
        return value

    def _load_manifest(self) -> dict:
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"packages": {}}
        except (OSError, ValueError):
            logger.warning("Firmware-Manifest ist nicht lesbar – alle Pakete gelten als nicht freigegeben.")
            return {"packages": {}}
        packages = data.get("packages") if isinstance(data, dict) else None
        return {"packages": packages if isinstance(packages, dict) else {}}

    def packages(self) -> list[FirmwarePackage]:
        manifest = self._load_manifest()["packages"]
        result = []
        for file in self.list_files():
            sha = self.hash_of(file.name)
            entry = manifest.get(file.name)
            pkg = FirmwarePackage(
                name=file.name,
                size_bytes=file.size_bytes,
                vendor=file.device_type,
                sha256=sha,
                filename_version=version_from_filename(file.name),
                status="unreleased",
            )
            if isinstance(entry, dict) and entry.get("vendor") == file.device_type:
                pkg.status = "released" if str(entry.get("sha256", "")).lower() == sha else "hash_mismatch"
                pkg.version = str(entry.get("version") or "") or None
                pkg.models = [str(m) for m in entry.get("models", []) if str(m).strip()]
                pkg.vendor_checksum_verified = bool(entry.get("vendor_checksum_verified"))
                pkg.stop_run_tested = bool(entry.get("stop_run_tested"))
                pkg.released_by = entry.get("released_by")
                pkg.released_at = entry.get("released_at")
                pkg.notes = entry.get("notes")
            result.append(pkg)
        return result

    def package(self, name: str) -> FirmwarePackage | None:
        return next((p for p in self.packages() if p.name == name), None)

    def release(
        self, name: str, *, version: str, models: list[str], vendor_sha256: str | None, released_by: str, notes: str | None
    ) -> FirmwarePackage:
        file = next((f for f in self.list_files() if f.name == name), None)
        if file is None:
            raise FirmwareFileNotFound()
        version = version.strip()
        if parse_version(version) is None:
            raise InvalidRelease("Die Zielversion muss eine Versionsnummer wie 2.3.4 enthalten.")
        models = [m.strip() for m in models if m.strip()]
        actual = self.hash_of(name, fresh=True)
        verified = False
        if vendor_sha256:
            expected = vendor_sha256.strip().lower()
            if len(expected) != 64 or not set(expected) <= _HEX:
                raise InvalidRelease("Die Hersteller-Prüfsumme muss ein SHA-256-Wert (64 Hex-Zeichen) sein.")
            if expected != actual:
                raise InvalidRelease("Die Datei stimmt nicht mit der Hersteller-Prüfsumme überein. Freigabe abgelehnt.")
            verified = True
        with self._lock:
            manifest = self._load_manifest()
            manifest["packages"][name] = {
                "vendor": file.device_type,
                "version": version,
                "sha256": actual,
                "models": models,
                "vendor_checksum_verified": verified,
                "stop_run_tested": False,
                "released_by": released_by,
                "released_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "notes": (notes or "").strip()[:500] or None,
            }
            self._write_manifest(manifest)
        logger.info("Firmwarepaket %s als Version %s freigegeben", name, version)
        pkg = self.package(name)
        assert pkg is not None
        return pkg

    def revoke(self, name: str) -> None:
        with self._lock:
            manifest = self._load_manifest()
            if manifest["packages"].pop(name, None) is not None:
                self._write_manifest(manifest)

    def _write_manifest(self, manifest: dict) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.manifest_path.parent, prefix=".manifest-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2, ensure_ascii=False, sort_keys=True)
            os.replace(tmp, self.manifest_path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
