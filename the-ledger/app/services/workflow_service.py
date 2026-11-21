"""Workflow service — the assessment state machine and its event bus.

States: ``DRAFT -> SUBMITTED -> APPROVED -> GENERATING -> READY``

Every job carries a ``reported_state``. The validator is supposed to check the
action against the assessment's *actual* state, but it evaluates the action
against the *reported* state instead. When a caller omits ``reported_state``
the actual state is used and everything behaves normally.
"""
from ..errors import ApiError
from ..models import Assessment, Event, Job
from ..security import new_id
from . import audit, report_service

# action -> (from_state, to_state)
TRANSITIONS = {
    "submit": ("DRAFT", "SUBMITTED"),
    "approve": ("SUBMITTED", "APPROVED"),
    "generate": ("APPROVED", "GENERATING"),
    "finalize": ("GENERATING", "READY"),
}

VALID_ACTIONS = sorted(TRANSITIONS)


def create_job(db, principal, assessment: Assessment, action: str, reported_state):
    rule = TRANSITIONS.get(action)
    if rule is None:
        raise ApiError(
            400,
            "unknown_action",
            f"'{action}' is not a recognised workflow action",
            {"valid_actions": VALID_ACTIONS},
        )
    from_state, to_state = rule
    actual = assessment.state

    # Idempotency: an action whose target state is already in place is a no-op.
    if actual == to_state:
        latest = (
            db.query(Job)
            .filter(Job.assessment_id == assessment.id, Job.action == action)
            .order_by(Job.created_at.desc())
            .first()
        )
        return {"job": latest, "event": None, "idempotent": True}

    # The state the transition is evaluated against. A caller may supply it;
    # otherwise the assessment's current state is used.
    evaluated = reported_state or actual

    if evaluated != from_state:
        raise ApiError(
            409,
            "invalid_transition",
            f"action '{action}' is only valid from state '{from_state}'",
            {
                "action": action,
                "evaluated_state": evaluated,
                "assessment_state": actual,
            },
        )

    job = Job(
        id=new_id("job"),
        assessment_id=assessment.id,
        action=action,
        reported_state=evaluated,
        actual_state=actual,
        outcome="completed",
        requested_by=principal.user.id,
        org_id=principal.active_org_id,
    )
    db.add(job)

    assessment.state = to_state
    db.commit()

    event = Event(
        id=new_id("evt"),
        type=f"assessment.{action}_requested",
        assessment_id=assessment.id,
        actor_user_id=principal.user.id,
        org_id=principal.active_org_id,
        payload={
            "assessment_id": assessment.id,
            "requested_by": principal.user.id,
            # The workflow asserts ownership to downstream consumers.
            "owner_user_id": principal.user.id,
            "origin_org": principal.active_org_id,
            "action": action,
            "from_state": evaluated,
            "to_state": to_state,
            "reported_state": reported_state,
        },
    )
    db.add(event)
    db.commit()

    report = report_service.consume_event(db, event, assessment)

    audit.record(
        db,
        org_id=principal.active_org_id,
        actor_user_id=principal.user.id,
        action=f"workflow.{action}",
        object_type="assessment",
        object_id=assessment.id,
        metadata={
            "job": job.id,
            "event": event.id,
            "reported_state": evaluated,
            "assessment_state": actual,
            "to_state": to_state,
        },
    )
    db.commit()

    return {"job": job, "event": event, "report": report, "idempotent": False}
