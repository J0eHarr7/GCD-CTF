"""Workflow API: jobs and the internal event stream.

Jobs are authorised against the session's active organisation. The event
stream is exposed read-only so that operators (and, as it turns out, players)
can observe what the workflow asserts to downstream services.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session as DbSession

from ..db import get_session
from ..errors import ApiError
from ..models import Assessment, Event, Job
from ..security import Principal, require_principal
from ..serializers import event_public, job_public
from ..services import workflow_service

router = APIRouter(prefix="/api/v1", tags=["workflow"])


class JobBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assessment_id: str
    action: str
    reported_state: Optional[str] = None


@router.post("/jobs")
def create_job(
    body: JobBody,
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    assessment = db.get(Assessment, body.assessment_id)
    if assessment is None or assessment.org_id != principal.active_org_id:
        raise ApiError(404, "assessment_not_found", "no such assessment")

    result = workflow_service.create_job(
        db, principal, assessment, body.action, body.reported_state
    )
    job = result["job"]
    return {
        "job": job_public(job) if job else None,
        "idempotent": result["idempotent"],
        "event": event_public(result["event"]) if result["event"] else None,
    }


@router.get("/jobs")
def list_jobs(
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    rows = (
        db.query(Job)
        .filter(Job.org_id == principal.active_org_id)
        .order_by(Job.created_at.desc())
        .all()
    )
    return {"organization_id": principal.active_org_id, "jobs": [job_public(j) for j in rows]}


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    job = db.get(Job, job_id)
    if job is None or job.org_id != principal.active_org_id:
        raise ApiError(404, "job_not_found", "no such job")
    events = [
        e
        for e in db.query(Event)
        .filter(Event.assessment_id == job.assessment_id)
        .order_by(Event.created_at)
        .all()
        if e.payload.get("action") == job.action
    ]
    return {"job": job_public(job), "events": [event_public(e) for e in events]}


@router.get("/events")
def list_events(
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    rows = (
        db.query(Event)
        .filter(Event.org_id == principal.active_org_id)
        .order_by(Event.created_at.desc())
        .all()
    )
    return {"organization_id": principal.active_org_id, "events": [event_public(e) for e in rows]}
