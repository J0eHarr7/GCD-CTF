"""Audit API and export requests.

The audit trail exists to be *read*. It shows what happened, who did it, and
which organisation the system attributed the action to.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session as DbSession

from ..db import get_session
from ..models import AuditRecord, ExportRequest
from ..security import Principal, new_id, require_principal
from ..serializers import audit_public, export_public
from ..services import audit

router = APIRouter(prefix="/api/v1", tags=["audit"])

_ALLOWED_DATASETS = {"audit", "events", "deliveries"}
_ALLOWED_FORMATS = {"json", "csv"}


class ExportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset: str = "audit"
    format: str = "json"


@router.get("/audit")
def list_audit(
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    rows = (
        db.query(AuditRecord)
        .filter(AuditRecord.org_id == principal.active_org_id)
        .order_by(AuditRecord.created_at.desc())
        .all()
    )
    return {
        "organization_id": principal.active_org_id,
        "audit": [audit_public(r) for r in rows],
    }


@router.post("/exports")
def create_export(
    body: ExportBody,
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    if body.dataset not in _ALLOWED_DATASETS:
        from ..errors import ApiError

        raise ApiError(
            400,
            "unsupported_dataset",
            "that dataset cannot be exported",
            {"allowed": sorted(_ALLOWED_DATASETS)},
        )
    if body.format not in _ALLOWED_FORMATS:
        from ..errors import ApiError

        raise ApiError(
            400, "unsupported_format", "that format is not supported"
        )

    export = ExportRequest(
        id=new_id("exp"),
        org_id=principal.active_org_id,
        dataset=body.dataset,
        format=body.format,
        requested_by=principal.user.id,
        state="QUEUED",
    )
    db.add(export)
    audit.record(
        db,
        org_id=principal.active_org_id,
        actor_user_id=principal.user.id,
        action="export.requested",
        object_type="export",
        object_id=export.id,
        metadata={"dataset": body.dataset, "format": body.format},
    )
    db.commit()
    return {"export": export_public(export)}


@router.get("/exports")
def list_exports(
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    rows = (
        db.query(ExportRequest)
        .filter(ExportRequest.org_id == principal.active_org_id)
        .order_by(ExportRequest.created_at.desc())
        .all()
    )
    return {
        "organization_id": principal.active_org_id,
        "exports": [export_public(e) for e in rows],
    }
