"""Firmwarepakete, Freigaben und Übersicht der Gerätetreiber."""

from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from backend import __version__
from backend.services.auth import Session

from .deps import Services, get_services, get_session, require_csrf
from .schemas import (
    DriverOut,
    FirmwareFileListOut,
    FirmwareFileOut,
    FirmwarePackageListOut,
    FirmwarePackageOut,
    ReleaseRequest,
    StrictModel,
    SystemOut,
)


class RevokeRequest(StrictModel):
    name: str = Field(min_length=1, max_length=255)


logger = logging.getLogger(__name__)
router = APIRouter(tags=["firmware"])


def _package_out(pkg) -> FirmwarePackageOut:
    data = asdict(pkg)
    data.pop("stop_run_tested", None)
    return FirmwarePackageOut(**data)


@router.get("/api/system", response_model=SystemOut)
def system_info(_: Session = Depends(get_session), services: Services = Depends(get_services)):
    return SystemOut(
        mode=services.settings.device_mode,
        version=__version__,
        drivers=[DriverOut(**d) for d in services.updates.driver_overview()],
    )


@router.get("/api/firmware/files", response_model=FirmwareFileListOut)
def list_firmware_files(_: Session = Depends(get_session), services: Services = Depends(get_services)):
    return FirmwareFileListOut(files=[FirmwareFileOut(**asdict(f)) for f in services.firmware.list_files()])


@router.get("/api/firmware/packages", response_model=FirmwarePackageListOut)
async def list_packages(_: Session = Depends(get_session), services: Services = Depends(get_services)):
    # SHA-256 großer Dateien wird beim ersten Aufruf berechnet → Thread-Pool.
    packages = await run_in_threadpool(services.firmware.packages)
    return FirmwarePackageListOut(packages=[_package_out(p) for p in packages])


@router.post("/api/firmware/packages/release", response_model=FirmwarePackageOut)
async def release_package(body: ReleaseRequest, session: Session = Depends(require_csrf), services: Services = Depends(get_services)):
    pkg = await run_in_threadpool(
        lambda: services.firmware.release(
            body.name,
            version=body.version,
            models=body.models,
            vendor_sha256=body.vendor_sha256,
            released_by=session.user.username,
            notes=body.notes,
        )
    )
    logger.info("Firmwarepaket freigegeben durch Benutzer-ID %s", session.user.id)
    return _package_out(pkg)


@router.post("/api/firmware/packages/revoke", response_model=FirmwarePackageListOut)
async def revoke_package(body: RevokeRequest, session: Session = Depends(require_csrf), services: Services = Depends(get_services)):
    services.firmware.revoke(body.name)
    logger.info("Freigabe für Firmwarepaket zurückgezogen durch Benutzer-ID %s", session.user.id)
    packages = await run_in_threadpool(services.firmware.packages)
    return FirmwarePackageListOut(packages=[_package_out(p) for p in packages])
