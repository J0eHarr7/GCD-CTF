"""Identity API: authentication, sessions, and the active organisation."""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session as DbSession

from ..db import get_session
from ..errors import ApiError
from ..models import Membership, Organization, Session, User
from ..security import (
    Principal,
    issue_session,
    require_principal,
    verify_password,
)
from ..serializers import org_public, session_public, user_public
from ..services import audit

router = APIRouter(prefix="/api/v1", tags=["identity"])


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    password: str


class SwitchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: str


def _memberships(db: DbSession, user_id: str):
    rows = db.query(Membership).filter(Membership.user_id == user_id).all()
    out = []
    for row in rows:
        org = db.get(Organization, row.org_id)
        out.append({"organization": org_public(org), "role": row.role})
    return out


def _principal_payload(db: DbSession, principal: Principal):
    active_org = db.get(Organization, principal.active_org_id)
    return {
        "user": user_public(principal.user),
        "active_org": org_public(active_org),
        "memberships": _memberships(db, principal.user.id),
        "session": session_public(principal.session, current=True),
    }


@router.post("/auth")
def login(
    body: LoginBody,
    request: Request,
    db: DbSession = Depends(get_session),
):
    user = (
        db.query(User).filter(User.email == body.email.strip().lower()).first()
    )
    if user is None or not verify_password(body.password, user.password_hash):
        raise ApiError(
            401, "invalid_credentials", "email or password is incorrect"
        )
    session = issue_session(db, user, request.headers.get("user-agent", ""))
    audit.record(
        db,
        org_id=user.default_org_id,
        actor_user_id=user.id,
        action="auth.login",
        object_type="session",
        object_id=session.token,
        metadata={"email": user.email},
    )
    db.commit()
    payload = _principal_payload(
        db, Principal(session=session, user=user)
    )
    payload["token"] = session.token
    payload["expires_in"] = session.expires_at
    return payload


@router.get("/auth")
def whoami(
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    return _principal_payload(db, principal)


@router.delete("/auth")
def logout(
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    principal.session.revoked = True
    audit.record(
        db,
        org_id=principal.active_org_id,
        actor_user_id=principal.user.id,
        action="auth.logout",
        object_type="session",
        object_id=principal.session.token,
    )
    db.commit()
    return {"revoked": True, "token": principal.session.token}


@router.get("/sessions")
def list_sessions(
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    rows = (
        db.query(Session)
        .filter(Session.user_id == principal.user.id)
        .order_by(Session.created_at.desc())
        .all()
    )
    return {
        "sessions": [
            session_public(s, current=(s.token == principal.session.token))
            for s in rows
        ]
    }


@router.post("/sessions/switch")
def switch_active_org(
    body: SwitchBody,
    principal: Principal = Depends(require_principal),
    db: DbSession = Depends(get_session),
):
    org = db.get(Organization, body.organization_id)
    if org is None:
        raise ApiError(404, "unknown_organization", "no such organisation")

    previous = principal.active_org_id
    principal.session.active_org_id = org.id
    audit.record(
        db,
        org_id=org.id,
        actor_user_id=principal.user.id,
        action="session.active_org_changed",
        object_type="session",
        object_id=principal.session.token,
        metadata={"from": previous, "to": org.id},
    )
    db.commit()
    return {
        "active_org": org_public(org),
        "previous_org_id": previous,
        "session": session_public(principal.session, current=True),
    }
