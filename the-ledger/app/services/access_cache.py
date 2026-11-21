"""Report access decisions and the derived-decision cache.

The report service is the only place that answers "may this principal read
this report?". It is split into two layers:

* ``authoritative_decision`` — compute from the *current* database state.
* ``decision_for`` — consult the persisted cache first, and only compute (and
  cache) when no decision is on file.

Only ALLOW decisions are cached. Nothing invalidates a cached decision when
the report's ownership changes.
"""
from ..models import AccessDecision, Report
from ..security import membership_role

ALLOW = "ALLOW"
DENY = "DENY"

# Roles that may read any report belonging to their organisation.
_ORG_READ_ROLES = {"manager", "admin"}


def authoritative_decision(db, user, report: Report):
    """Compute the decision from authoritative state alone."""
    if report.owner_user_id == user.id:
        return ALLOW, "owner"
    role = membership_role(db, user.id, report.org_id)
    if role in _ORG_READ_ROLES:
        return ALLOW, f"organisation role: {role}"
    if role:
        return DENY, f"role '{role}' may not read {report.classification} reports"
    return DENY, "not the owner and not a member of the owning organisation"


def cached_decision(db, user, report: Report):
    return (
        db.query(AccessDecision)
        .filter(
            AccessDecision.subject_user_id == user.id,
            AccessDecision.report_id == report.id,
        )
        .first()
    )


def decision_for(db, user, report: Report):
    """Return ``(decision, source, reason)``.

    ``source`` is ``"cache"`` when a previously persisted decision answered the
    request, or ``"computed"`` when the decision was derived from live state.
    """
    hit = cached_decision(db, user, report)
    if hit is not None:
        return hit.decision, "cache", hit.reason

    decision, reason = authoritative_decision(db, user, report)
    if decision == ALLOW:
        db.add(
            AccessDecision(
                subject_user_id=user.id,
                report_id=report.id,
                decision=ALLOW,
                reason=reason,
            )
        )
        db.commit()
    return decision, "computed", reason
