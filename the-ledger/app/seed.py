"""Deterministic seed data and reset.

A fresh deployment always produces the same fixture: two organisations, four
principals (two of them usable), three projects, four assessments, a small
history of workflow jobs / events / audit records, and one confidential
report that holds the flag.
"""
from datetime import datetime, timedelta, timezone

import secrets
from sqlalchemy import delete

from .db import Base, SessionLocal, create_all, drop_all
from .models import (
    Assessment,
    AuditRecord,
    Delivery,
    Event,
    ExportRequest,
    Job,
    Membership,
    Organization,
    Project,
    Report,
    Session,
    User,
)
from .security import hash_password

BASE = datetime(2026, 5, 1, 9, 0, 0, tzinfo=timezone.utc)


def ts(minutes: int) -> str:
    return (BASE + timedelta(minutes=minutes)).isoformat()


def _clear(db):
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(delete(table))
    db.commit()


def seed(db):
    _clear(db)

    # --- organisations -----------------------------------------------------
    orgs = [
        Organization(id="org_helios", name="Helios Audit Group", slug="helios"),
        Organization(
            id="org_vantage", name="Vantage Confidential", slug="vantage"
        ),
    ]
    db.add_all(orgs)
    db.flush()

    # --- principals --------------------------------------------------------
    users = [
        User(
            id="usr_alice",
            email="joeharry@helios.bat",
            display_name="Alice Moreau",
            password_hash=hash_password("joeharry-helios-1998"),
            default_org_id="org_helios",
            created_at=ts(0),
        ),
        User(
            id="usr_erin",
            email="erin@helios.example",
            display_name="Erin Nakamura",
            # Managers exist in the fixture but their credentials are random
            # and never distributed: their accounts cannot be logged into.
            password_hash=hash_password(secrets.token_urlsafe(32)),
            default_org_id="org_helios",
            created_at=ts(0),
        ),
        User(
            id="usr_carol",
            email="carol@vantage.example",
            display_name="Carol Voss",
            password_hash=hash_password("carol-vantage-2026"),
            default_org_id="org_vantage",
            created_at=ts(0),
        ),
        User(
            id="usr_dave",
            email="dave@vantage.example",
            display_name="Dave Reyes",
            # See note on usr_erin: random, non-distributed credentials.
            password_hash=hash_password(secrets.token_urlsafe(32)),
            default_org_id="org_vantage",
            created_at=ts(0),
        ),
    ]
    db.add_all(users)
    db.flush()

    memberships = [
        Membership(user_id="usr_alice", org_id="org_helios", role="analyst"),
        Membership(user_id="usr_erin", org_id="org_helios", role="manager"),
        Membership(user_id="usr_carol", org_id="org_vantage", role="analyst"),
        Membership(user_id="usr_dave", org_id="org_vantage", role="manager"),
    ]
    db.add_all(memberships)
    db.flush()

    # --- projects ----------------------------------------------------------
    projects = [
        Project(
            id="prj_helios_q1",
            org_id="org_helios",
            name="Q1 External Assessment Programme",
            visibility="standard",
            created_at=ts(1),
        ),
        Project(
            id="prj_helios_int",
            org_id="org_helios",
            name="Internal Hardening",
            visibility="standard",
            created_at=ts(2),
        ),
        Project(
            id="prj_vantage_atlas",
            org_id="org_vantage",
            name="Atlas Programme",
            visibility="standard",
            created_at=ts(3),
        ),
        Project(
            id="prj_vantage_black",
            org_id="org_vantage",
            name="Black Vault",
            visibility="restricted",
            created_at=ts(4),
        ),
    ]
    db.add_all(projects)
    db.flush()

    # --- assessments -------------------------------------------------------
    assessments = [
        Assessment(
            id="asm_helios_web",
            project_id="prj_helios_q1",
            org_id="org_helios",
            title="Helios Customer Portal",
            classification="INTERNAL",
            state="APPROVED",
            created_by="usr_alice",
            created_at=ts(5),
        ),
        Assessment(
            id="asm_helios_net",
            project_id="prj_helios_int",
            org_id="org_helios",
            title="Helios Core Network",
            classification="INTERNAL",
            state="DRAFT",
            created_by="usr_alice",
            created_at=ts(6),
        ),
        Assessment(
            id="asm_vantage_api",
            project_id="prj_vantage_atlas",
            org_id="org_vantage",
            title="Atlas Public API",
            classification="CONFIDENTIAL",
            state="SUBMITTED",
            created_by="usr_carol",
            created_at=ts(7),
        ),
        Assessment(
            id="asm_conf",
            project_id="prj_vantage_black",
            org_id="org_vantage",
            title="Project Nightfall",
            classification="TOP_SECRET",
            state="READY",
            created_by="usr_dave",
            created_at=ts(8),
        ),
    ]
    db.add_all(assessments)
    db.flush()

    # --- the confidential report (holds the flag) --------------------------
    report = Report(
        id="rep_conf_nightfall",
        assessment_id="asm_conf",
        org_id="org_vantage",
        owner_user_id="usr_dave",
        title="Project Nightfall — Confidential Assessment",
        classification="TOP_SECRET",
        state="READY",
        contains_flag=True,
        created_at=ts(30),
        updated_at=ts(42),
        body=(
            "CONFIDENTIAL — Project Nightfall\n"
            "Assessed tenant: Vantage Confidential (vantage)\n"
            "Classification: TOP SECRET\n"
            "Assessment window: 2026-03-01 to 2026-04-30\n"
            "\n"
            "Findings (summary):\n"
            "  1. Three long-lived service accounts shared a single key.\n"
            "  2. The settlement service accepted caller-asserted ownership.\n"
            "  3. An access decision was cached and never invalidated.\n"
            "\n"
            "Distribution is restricted to the assessment owner and to Vantage\n"
            "managers. Do not forward outside the organisation.\n"
            "\n"
            "Verification key: {{FLAG}}\n"
        ),
    )
    db.add(report)
    db.flush()

    # --- benign workflow history ------------------------------------------
    jobs = [
        Job(
            id="job_submit_atlas",
            assessment_id="asm_vantage_api",
            action="submit",
            reported_state="DRAFT",
            actual_state="DRAFT",
            outcome="completed",
            requested_by="usr_carol",
            org_id="org_vantage",
            created_at=ts(10),
        ),
        Job(
            id="job_gen_nightfall",
            assessment_id="asm_conf",
            action="generate",
            reported_state="APPROVED",
            actual_state="APPROVED",
            outcome="completed",
            requested_by="usr_dave",
            org_id="org_vantage",
            created_at=ts(20),
        ),
        Job(
            id="job_fin_nightfall",
            assessment_id="asm_conf",
            action="finalize",
            reported_state="GENERATING",
            actual_state="GENERATING",
            outcome="completed",
            requested_by="usr_dave",
            org_id="org_vantage",
            created_at=ts(40),
        ),
    ]
    db.add_all(jobs)

    events = [
        Event(
            id="evt_submit_atlas",
            type="assessment.submit_requested",
            assessment_id="asm_vantage_api",
            actor_user_id="usr_carol",
            org_id="org_vantage",
            payload={
                "assessment_id": "asm_vantage_api",
                "requested_by": "usr_carol",
                "owner_user_id": "usr_carol",
                "origin_org": "org_vantage",
                "action": "submit",
                "from_state": "DRAFT",
                "to_state": "SUBMITTED",
                "reported_state": None,
            },
            created_at=ts(11),
        ),
        Event(
            id="evt_gen_nightfall",
            type="assessment.generate_requested",
            assessment_id="asm_conf",
            actor_user_id="usr_dave",
            org_id="org_vantage",
            payload={
                "assessment_id": "asm_conf",
                "requested_by": "usr_dave",
                "owner_user_id": "usr_dave",
                "origin_org": "org_vantage",
                "action": "generate",
                "from_state": "APPROVED",
                "to_state": "GENERATING",
                "reported_state": "APPROVED",
            },
            created_at=ts(21),
        ),
        Event(
            id="evt_fin_nightfall",
            type="assessment.finalize_requested",
            assessment_id="asm_conf",
            actor_user_id="usr_dave",
            org_id="org_vantage",
            payload={
                "assessment_id": "asm_conf",
                "requested_by": "usr_dave",
                "owner_user_id": "usr_dave",
                "origin_org": "org_vantage",
                "action": "finalize",
                "from_state": "GENERATING",
                "to_state": "READY",
                "reported_state": "GENERATING",
            },
            created_at=ts(41),
        ),
    ]
    db.add_all(events)

    # --- audit trail --------------------------------------------------------
    audit = [
        AuditRecord(
            id="aud_0001",
            org_id="org_helios",
            actor_user_id="usr_alice",
            action="auth.login",
            object_type="session",
            object_id="sess_seed_alice",
            metadata_json={"email": "joeharry@helios.bat"},
            created_at=ts(9),
        ),
        AuditRecord(
            id="aud_0002",
            org_id="org_vantage",
            actor_user_id="usr_carol",
            action="assessment.created",
            object_type="assessment",
            object_id="asm_vantage_api",
            metadata_json={"title": "Atlas Public API"},
            created_at=ts(7),
        ),
        AuditRecord(
            id="aud_0003",
            org_id="org_vantage",
            actor_user_id="usr_carol",
            action="workflow.submit",
            object_type="assessment",
            object_id="asm_vantage_api",
            metadata_json={
                "job": "job_submit_atlas",
                "reported_state": "DRAFT",
                "to_state": "SUBMITTED",
            },
            created_at=ts(11),
        ),
        AuditRecord(
            id="aud_0004",
            org_id="org_vantage",
            actor_user_id="usr_carol",
            action="workflow.generate",
            object_type="assessment",
            object_id="asm_vantage_api",
            metadata_json={
                "outcome": "rejected",
                "code": "invalid_transition",
                "evaluated_state": "SUBMITTED",
                "expected_state": "APPROVED",
            },
            created_at=ts(12),
        ),
        AuditRecord(
            id="aud_0005",
            org_id="org_vantage",
            actor_user_id="usr_dave",
            action="workflow.generate",
            object_type="assessment",
            object_id="asm_conf",
            metadata_json={
                "job": "job_gen_nightfall",
                "reported_state": "APPROVED",
                "to_state": "GENERATING",
            },
            created_at=ts(21),
        ),
        AuditRecord(
            id="aud_0006",
            org_id="org_vantage",
            actor_user_id="usr_dave",
            action="workflow.finalize",
            object_type="assessment",
            object_id="asm_conf",
            metadata_json={
                "job": "job_fin_nightfall",
                "reported_state": "GENERATING",
                "to_state": "READY",
            },
            created_at=ts(41),
        ),
        AuditRecord(
            id="aud_0007",
            org_id="org_vantage",
            actor_user_id="usr_dave",
            action="report.finalized",
            object_type="report",
            object_id="rep_conf_nightfall",
            metadata_json={
                "owner_user_id": "usr_dave",
                "event": "evt_fin_nightfall",
            },
            created_at=ts(42),
        ),
    ]
    db.add_all(audit)

    db.commit()
    return db


def reset_all():
    drop_all()
    create_all()
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
