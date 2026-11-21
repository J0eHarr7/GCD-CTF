"""The Ledger data model.

The challenge turns on the difference between several things that all look
like "who owns this": the authenticated user, their organisation membership,
the session's *active* organisation, and the organisation recorded on an
individual resource. The schema keeps them separate on purpose.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    # The organisation the principal belongs to by default (a membership).
    default_org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id"), nullable=False
    )
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "org_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id"), nullable=False
    )
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # analyst|manager|admin


class Session(Base):
    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id"), nullable=False
    )
    # The organisation this session is currently acting for. Changing it is a
    # security-relevant act.
    active_org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id"), nullable=False
    )
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    user_agent: Mapped[str] = mapped_column(String(200), default="")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="standard")
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("projects.id"), nullable=False
    )
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    classification: Mapped[str] = mapped_column(String(20), default="INTERNAL")
    state: Mapped[str] = mapped_column(String(20), default="DRAFT")
    created_by: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("assessments.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    # The state the workflow actually evaluated. Kept for display so operators
    # can see what a requester asserted.
    reported_state: Mapped[str] = mapped_column(String(20), nullable=False)
    actual_state: Mapped[str] = mapped_column(String(20), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), default="completed")
    requested_by: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id"), nullable=False
    )
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id"), nullable=False
    )
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class Event(Base):
    """Internal workflow events. Emitted by the workflow service, consumed by
    the report service."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    assessment_id: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(String(40), nullable=False)
    org_id: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class AuditRecord(Base):
    __tablename__ = "audit_records"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(String(40), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    object_type: Mapped[str] = mapped_column(String(40), nullable=False)
    object_id: Mapped[str] = mapped_column(String(60), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("assessments.id"), nullable=False
    )
    org_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("organizations.id"), nullable=False
    )
    # Owner is a single user, not an organisation. This is what the report
    # access decision is derived from.
    owner_user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    classification: Mapped[str] = mapped_column(String(20), default="INTERNAL")
    state: Mapped[str] = mapped_column(String(20), default="GENERATING")  # GENERATING|READY
    body: Mapped[str] = mapped_column(Text, default="")
    contains_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class AccessDecision(Base):
    """The report service's derived access cache.

    Only ALLOW decisions are cached. Once written, a decision is not
    invalidated when the underlying report ownership changes.
    """

    __tablename__ = "access_decisions"
    __table_args__ = (UniqueConstraint("subject_user_id", "report_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_user_id: Mapped[str] = mapped_column(String(40), nullable=False)
    report_id: Mapped[str] = mapped_column(String(40), nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)  # ALLOW
    reason: Mapped[str] = mapped_column(String(120), default="")
    computed_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class ExportRequest(Base):
    __tablename__ = "export_requests"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(40), nullable=False)
    dataset: Mapped[str] = mapped_column(String(40), nullable=False)
    format: Mapped[str] = mapped_column(String(20), default="json")
    requested_by: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="QUEUED")
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    report_id: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient: Mapped[str] = mapped_column(String(160), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="QUEUED")  # QUEUED|SENT
    created_at: Mapped[str] = mapped_column(String(40), default=now_iso)
