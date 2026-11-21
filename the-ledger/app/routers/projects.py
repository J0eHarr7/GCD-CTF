"""Project and assessment API.

Note the deliberate inconsistency between the two list endpoints:

* ``/projects`` is scoped by the principal's *default organisation* — the
  membership recorded on the user. It is not affected by the session's active
  organisation.
* ``/assessments`` is scoped by the session's *active organisation*.

The two endpoints therefore disagree about which tenant the caller is acting
for, which is the first seam in the challenge.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from ..db import get_session
from ..errors import ApiError
from ..models import Assessment, Project, Report
from ..security import Principal, membership_role, require_principal
from ..serializers import assessment_public, project_public

router = APIRouter(prefix="/api/v1", tags=["projects"])

_MANAGER_ROLES = {"manager", "admin"}


def _report_id_for(db: DbSession, assessment_id: str):
    row = (
        db.query(Report)
        .filter(Report.assessment_id == assessment_id)
        .order_by(Report.created_at.desc())
        .first()
    )
    return row.id if row else None


@router.get("/projects")
def list_projects(
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    org_id = principal.user.default_org_id
    role = membership_role(db, principal.user.id, org_id)
    projects = (
        db.query(Project)
        .filter(Project.org_id == org_id)
        .order_by(Project.created_at)
        .all()
    )
    visible = [
        p
        for p in projects
        if p.visibility == "standard" or role in _MANAGER_ROLES
    ]
    return {
        "organization_id": org_id,
        "scope": "principal.default_org_id",
        "projects": [project_public(p) for p in visible],
    }


@router.get("/projects/{project_id}")
def get_project(
    project_id: str,
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    project = db.get(Project, project_id)
    if project is None:
        raise ApiError(404, "project_not_found", "no such project")
    if project.org_id != principal.user.default_org_id:
        # Authoritative, membership-based check: cross-tenant is simply "not
        # found".
        raise ApiError(404, "project_not_found", "no such project")
    role = membership_role(db, principal.user.id, project.org_id)
    if project.visibility == "restricted" and role not in _MANAGER_ROLES:
        raise ApiError(
            403, "forbidden", "this project is restricted to managers"
        )
    return {"project": project_public(project)}


@router.get("/assessments")
def list_assessments(
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    org_id = principal.active_org_id
    rows = (
        db.query(Assessment)
        .filter(Assessment.org_id == org_id)
        .order_by(Assessment.created_at)
        .all()
    )
    return {
        "organization_id": org_id,
        "scope": "session.active_org_id",
        "assessments": [
            assessment_public(a, report_id=_report_id_for(db, a.id)) for a in rows
        ],
    }


@router.get("/assessments/{assessment_id}")
def get_assessment(
    assessment_id: str,
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    assessment = db.get(Assessment, assessment_id)
    if assessment is None or assessment.org_id != principal.active_org_id:
        raise ApiError(404, "assessment_not_found", "no such assessment")
    return {
        "assessment": assessment_public(
            assessment, report_id=_report_id_for(db, assessment.id)
        )
    }
