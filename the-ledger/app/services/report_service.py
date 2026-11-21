"""Report service.

Consumes workflow events and maintains report records. The asymmetry between
how it treats a *generation* event and a *finalisation* event is the internal
trust boundary the challenge is built around:

* On ``assessment.generate_requested`` it takes the report owner from the
  event payload (``owner_user_id``), i.e. it trusts the workflow's claim.
* On ``assessment.finalize_requested`` it re-derives the owner from the
  authoritative assessment record.

The first path is the one that was never hardened during the migration.
"""
from ..config import flag
from ..models import Assessment, Event, Report, now_iso
from ..security import new_id
from . import audit

REDACTED_DRAFT = (
    "[DRAFT IN PROGRESS — the final content is withheld until the assessment "
    "is finalized]"
)


def find_report_for_assessment(db, assessment_id: str):
    return (
        db.query(Report)
        .filter(Report.assessment_id == assessment_id)
        .order_by(Report.created_at.desc())
        .first()
    )


def _generate(db, event: Event, assessment: Assessment) -> Report:
    # The workflow service is trusted to have already authorised this action,
    # so its ownership claim is taken at face value.
    owner = event.payload.get("owner_user_id") or event.payload.get("requested_by")
    report = find_report_for_assessment(db, assessment.id)
    if report is None:
        report = Report(
            id=new_id("rep"),
            assessment_id=assessment.id,
            org_id=event.payload.get("origin_org", assessment.org_id),
            owner_user_id=owner,
            title=f"Assessment Report — {assessment.title}",
            classification=assessment.classification,
            state="GENERATING",
            body="This report is still being generated.",
            contains_flag=False,
        )
        db.add(report)
    else:
        report.owner_user_id = owner
        report.state = "GENERATING"
        report.updated_at = now_iso()

    audit.record(
        db,
        org_id=assessment.org_id,
        actor_user_id=event.actor_user_id,
        action="report.generation_started",
        object_type="report",
        object_id=report.id,
        metadata={"owner_user_id": owner, "event": event.id},
    )
    return report


def _finalize(db, event: Event, assessment: Assessment) -> Report:
    report = find_report_for_assessment(db, assessment.id)
    if report is None:
        return None
    # Ownership is re-derived from the authoritative assessment record, not
    # from the event.
    report.owner_user_id = assessment.created_by
    report.state = "READY"
    report.updated_at = now_iso()
    audit.record(
        db,
        org_id=assessment.org_id,
        actor_user_id=event.actor_user_id,
        action="report.finalized",
        object_type="report",
        object_id=report.id,
        metadata={"owner_user_id": report.owner_user_id, "event": event.id},
    )
    return report


def consume_event(db, event: Event, assessment: Assessment):
    """Synchronously process a workflow event. Deterministic by design."""
    report = None
    if event.type == "assessment.generate_requested":
        report = _generate(db, event, assessment)
    elif event.type == "assessment.finalize_requested":
        report = _finalize(db, event, assessment)
    db.commit()
    return report


def render_body(report: Report) -> str:
    """Render the report body. The flag is emitted only for a READY report."""
    if not report.contains_flag:
        return report.body
    if report.state == "READY":
        return report.body.replace("{{FLAG}}", flag())
    return REDACTED_DRAFT
