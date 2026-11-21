"""Report API — the final access decision.

``GET /api/v1/reports/{id}`` is the only place a report body is returned. It
consults the report service's decision cache *before* computing a decision
from live state, which is what makes a previously cached ALLOW survive a
later ownership change.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session as DbSession

from ..db import get_session
from ..errors import ApiError
from ..models import Delivery, Report
from ..security import Principal, new_id, require_principal
from ..serializers import delivery_public, report_public
from ..services import access_cache, audit, report_service

router = APIRouter(prefix="/api/v1", tags=["reports"])


class DeliveryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipient: str


@router.get("/reports")
def list_reports(
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    rows = db.query(Report).order_by(Report.created_at).all()
    visible = []
    for report in rows:
        decision, reason = access_cache.authoritative_decision(
            db, principal.user, report
        )
        if decision == access_cache.ALLOW:
            visible.append(report_public(report))
    return {"reports": visible}


@router.get("/reports/{report_id}")
def get_report(
    report_id: str,
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    report = db.get(Report, report_id)
    if report is None:
        raise ApiError(404, "report_not_found", "no such report")

    decision, source, reason = access_cache.decision_for(
        db, principal.user, report
    )
    if decision != access_cache.ALLOW:
        raise ApiError(
            403,
            "report_access_denied",
            "you are not entitled to this report",
            {"decision": decision, "reason": reason},
        )

    body = report_service.render_body(report)
    return {
        "report": report_public(
            report,
            body=body,
            access={"decision": decision, "source": source, "reason": reason},
        )
    }


@router.post("/reports/{report_id}/deliveries")
def create_delivery(
    report_id: str,
    body: DeliveryBody,
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    report = db.get(Report, report_id)
    if report is None:
        raise ApiError(404, "report_not_found", "no such report")
    decision, source, reason = access_cache.decision_for(
        db, principal.user, report
    )
    if decision != access_cache.ALLOW:
        raise ApiError(403, "report_access_denied", "you are not entitled to this report")

    delivery = Delivery(
        id=new_id("dlv"),
        report_id=report.id,
        recipient=body.recipient,
        requested_by=principal.user.id,
        state="SENT",
    )
    db.add(delivery)
    audit.record(
        db,
        org_id=report.org_id,
        actor_user_id=principal.user.id,
        action="report.delivered",
        object_type="delivery",
        object_id=delivery.id,
        metadata={"report_id": report.id, "recipient": body.recipient},
    )
    db.commit()
    return {"delivery": delivery_public(delivery), "access": {"source": source, "reason": reason}}


@router.get("/deliveries")
def list_deliveries(
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    rows = (
        db.query(Delivery)
        .filter(Delivery.requested_by == principal.user.id)
        .order_by(Delivery.created_at.desc())
        .all()
    )
    return {"deliveries": [delivery_public(d) for d in rows]}
