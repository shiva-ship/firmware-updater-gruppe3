"""Geräteinventar, Updatepläne, Dry-Run, Freigabe und Ausführung von Firmwareupdates."""

from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from backend.errors import DeviceNotFound, InvalidMasterPassword, TooManyAttempts
from backend.services.auth import Session
from backend.services.updates.service import Plan

from .deps import Services, get_services, get_session, require_csrf
from .schemas import (
    AuthorizeOut,
    AuthorizeRequest,
    DeviceStatusOut,
    ExecuteRequest,
    InventoryOut,
    JobOut,
    NotesOut,
    PlanOut,
    PrepareRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["updates"])


def _plan_out(plan: Plan, services: Services) -> PlanOut:
    counts = {k: 0 for k in ("ready", "up_to_date", "blocked", "no_driver")}
    for item in plan.items:
        counts[item.status] += 1
    caps = services.updates.capabilities()
    return PlanOut(
        id=plan.id,
        db_id=plan.db_id,
        mode=services.settings.device_mode,
        simulated=plan.simulated,
        created_at=plan.created_at,
        items=[i.to_dict() for i in plan.items],
        counts=counts,
        requires_stop_run=any(
            caps.get(i.vendor or "") is not None and caps[i.vendor or ""].requires_stop_run for i in plan.ready_items
        ),
        credentials_ready=services.updates.credentials_ready(plan),
    )


def _unlock_guard(services: Services, session: Session, db_id: str):
    """Gleiches Limit wie beim Entsperren, damit das Masterpasswort nicht hierüber erraten werden kann."""
    key = f"unlock:{session.user.id}:{db_id}"
    retry_after = services.unlock_limiter.retry_after(key)
    if retry_after > 0:
        raise TooManyAttempts(retry_after)
    return key


@router.get("/api/databases/{db_id}/entries/{entry_id}/notes", response_model=NotesOut)
def get_notes(db_id: str, entry_id: str, session: Session = Depends(get_session), services: Services = Depends(get_services)):
    _, root = services.keepass.get_tree(db_id, session.session_id, session.user.id)
    if not any(e.id == entry_id for e, _ in root.iter_entries_with_path()):
        raise DeviceNotFound()
    notes = services.keepass.get_notes(db_id, session.session_id, session.user.id, entry_id)
    return NotesOut(notes=notes[0] if notes else None, redacted=bool(notes and notes[1]))


@router.get("/api/databases/{db_id}/inventory", response_model=InventoryOut)
def get_inventory(db_id: str, session: Session = Depends(get_session), services: Services = Depends(get_services)):
    services.keepass.get_tree(db_id, session.session_id, session.user.id)
    inventory = services.updates.inventory(session.session_id, db_id)
    return InventoryOut(
        mode=services.settings.device_mode,
        devices={k: DeviceStatusOut(**asdict(v)) for k, v in inventory.items()},
    )


@router.post("/api/databases/{db_id}/update-plans", response_model=PlanOut)
async def prepare_updates(
    db_id: str, body: PrepareRequest, session: Session = Depends(require_csrf), services: Services = Depends(get_services)
):
    services.keepass.get(db_id, session.session_id, session.user.id)
    key = _unlock_guard(services, session, db_id)
    password = body.master_password.get_secret_value() if body.master_password else None
    try:
        plan = await run_in_threadpool(
            services.updates.prepare, db_id, session.session_id, session.user.id, body.entry_ids, password
        )
    except InvalidMasterPassword:
        services.unlock_limiter.register_failure(key)
        raise
    if password:
        services.unlock_limiter.reset(key)
    return _plan_out(plan, services)


@router.get("/api/update-plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: str, session: Session = Depends(get_session), services: Services = Depends(get_services)):
    return _plan_out(services.updates.get_plan(plan_id, session.session_id, session.user.id), services)


@router.post("/api/update-plans/{plan_id}/dry-run", response_model=JobOut)
def start_dry_run(plan_id: str, session: Session = Depends(require_csrf), services: Services = Depends(get_services)):
    job = services.updates.start_dry_run(plan_id, session.session_id, session.user.id)
    return services.updates.snapshot(job)


@router.post("/api/update-plans/{plan_id}/authorize", response_model=AuthorizeOut)
async def authorize_plan(
    plan_id: str, body: AuthorizeRequest, session: Session = Depends(require_csrf), services: Services = Depends(get_services)
):
    plan = services.updates.get_plan(plan_id, session.session_id, session.user.id)
    password = body.master_password.get_secret_value() if body.master_password else None
    if password is None:
        auth = services.updates.authorize(plan_id, session.session_id, session.user.id, None)
        return AuthorizeOut(authorization_id=auth.id, expires_in_seconds=services.settings.authorization_ttl_seconds)
    key = _unlock_guard(services, session, plan.db_id)
    try:
        auth = await run_in_threadpool(services.updates.authorize, plan_id, session.session_id, session.user.id, password)
    except InvalidMasterPassword:
        services.unlock_limiter.register_failure(key)
        raise
    services.unlock_limiter.reset(key)
    return AuthorizeOut(authorization_id=auth.id, expires_in_seconds=services.settings.authorization_ttl_seconds)


@router.post("/api/update-plans/{plan_id}/execute", response_model=JobOut)
def execute_plan(
    plan_id: str, body: ExecuteRequest, session: Session = Depends(require_csrf), services: Services = Depends(get_services)
):
    job = services.updates.execute(
        plan_id, session.session_id, session.user.id, body.authorization_id, body.approve_plc_stop_run
    )
    logger.info("Update-Auftrag %s gestartet durch Benutzer-ID %s", job.id, session.user.id)
    return services.updates.snapshot(job)


@router.get("/api/update-jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, session: Session = Depends(get_session), services: Services = Depends(get_services)):
    return services.updates.snapshot(services.updates.get_job(job_id, session.user.id))


@router.post("/api/update-jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: str, session: Session = Depends(require_csrf), services: Services = Depends(get_services)):
    return services.updates.snapshot(services.updates.cancel_job(job_id, session.user.id))
