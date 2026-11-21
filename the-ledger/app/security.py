"""Authentication: password hashing, bearer sessions, and the request
principal dependency.

A principal is deliberately *not* the same thing as an organisation. A
principal holds a session, and a session carries an ``active_org_id`` that
the client can change. Several endpoints later disagree about which of the
two is authoritative.
"""
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, Header
from sqlalchemy.orm import Session as DbSession

from .config import SESSION_TTL_SECONDS
from .db import get_session
from .errors import ApiError
from .models import Membership, Session, User

_PBKDF2_ROUNDS = 120_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ROUNDS
    ).hex()
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, rounds, salt, digest = stored.split("$")
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(rounds)
        ).hex()
        return hmac.compare_digest(candidate, digest)
    except Exception:
        return False


def new_token(prefix: str = "sess") -> str:
    return f"{prefix}_{secrets.token_urlsafe(24)}"


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def unix_now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def issue_session(db: DbSession, user: User, user_agent: str = "") -> Session:
    session = Session(
        token=new_token("sess"),
        user_id=user.id,
        active_org_id=user.default_org_id,
        expires_at=unix_now() + SESSION_TTL_SECONDS,
        user_agent=(user_agent or "")[:200],
    )
    db.add(session)
    db.commit()
    return session


def membership_role(db: DbSession, user_id: str, org_id: str):
    row = (
        db.query(Membership)
        .filter(Membership.user_id == user_id, Membership.org_id == org_id)
        .first()
    )
    return row.role if row else None


@dataclass
class Principal:
    session: Session
    user: User

    @property
    def active_org_id(self) -> str:
        return self.session.active_org_id


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "unauthenticated", "a Bearer token is required")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise ApiError(401, "unauthenticated", "malformed Authorization header")
    return token


def require_principal(
    authorization: str | None = Header(default=None),
    db: DbSession = Depends(get_session),
) -> Principal:
    token = _extract_bearer(authorization)
    session = db.get(Session, token)
    if session is None:
        raise ApiError(401, "invalid_session", "the session token is not recognised")
    if session.revoked:
        raise ApiError(401, "revoked_session", "this session has been revoked")
    if session.expires_at < unix_now():
        raise ApiError(401, "expired_session", "this session has expired")
    user = db.get(User, session.user_id)
    if user is None:
        raise ApiError(401, "invalid_session", "the session principal no longer exists")
    return Principal(session=session, user=user)
