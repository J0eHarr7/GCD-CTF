"""Response shaping. Keeps internal fields (password hashes, tokens) out of
responses and gives every resource a stable public shape."""


def org_public(org):
    if org is None:
        return None
    return {"id": org.id, "name": org.name, "slug": org.slug}


def user_public(user):
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "default_org_id": user.default_org_id,
    }


def membership_public(org, role):
    return {"organization": org_public(org), "role": role}


def session_public(session, current=False):
    return {
        "token": session.token if current else session.token[:12] + "…",
        "active_org_id": session.active_org_id,
        "created_at": session.created_at,
        "expires_at": session.expires_at,
        "revoked": session.revoked,
        "current": current,
    }


def project_public(project):
    return {
        "id": project.id,
        "org_id": project.org_id,
        "name": project.name,
        "visibility": project.visibility,
        "created_at": project.created_at,
    }


def assessment_public(assessment, report_id=None):
    return {
        "id": assessment.id,
        "project_id": assessment.project_id,
        "org_id": assessment.org_id,
        "title": assessment.title,
        "classification": assessment.classification,
        "state": assessment.state,
        "created_by": assessment.created_by,
        "report_id": report_id,
        "created_at": assessment.created_at,
    }


def job_public(job):
    return {
        "id": job.id,
        "assessment_id": job.assessment_id,
        "action": job.action,
        "outcome": job.outcome,
        "reported_state": job.reported_state,
        "actual_state": job.actual_state,
        "requested_by": job.requested_by,
        "org_id": job.org_id,
        "created_at": job.created_at,
    }


def event_public(event):
    return {
        "id": event.id,
        "type": event.type,
        "assessment_id": event.assessment_id,
        "actor_user_id": event.actor_user_id,
        "org_id": event.org_id,
        "payload": event.payload,
        "created_at": event.created_at,
    }


def report_public(report, body=None, access=None):
    data = {
        "id": report.id,
        "assessment_id": report.assessment_id,
        "org_id": report.org_id,
        "owner_user_id": report.owner_user_id,
        "title": report.title,
        "classification": report.classification,
        "state": report.state,
        "updated_at": report.updated_at,
    }
    if body is not None:
        data["body"] = body
    if access is not None:
        data["access"] = access
    return data


def audit_public(record):
    return {
        "id": record.id,
        "org_id": record.org_id,
        "actor_user_id": record.actor_user_id,
        "action": record.action,
        "object_type": record.object_type,
        "object_id": record.object_id,
        "metadata": record.metadata_json,
        "created_at": record.created_at,
    }


def delivery_public(delivery):
    return {
        "id": delivery.id,
        "report_id": delivery.report_id,
        "recipient": delivery.recipient,
        "requested_by": delivery.requested_by,
        "state": delivery.state,
        "created_at": delivery.created_at,
    }


def export_public(export):
    return {
        "id": export.id,
        "org_id": export.org_id,
        "dataset": export.dataset,
        "format": export.format,
        "requested_by": export.requested_by,
        "state": export.state,
        "created_at": export.created_at,
    }
