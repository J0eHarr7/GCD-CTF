"""Audit trail writer."""
from ..models import AuditRecord
from ..security import new_id


def record(db, org_id, actor_user_id, action, object_type, object_id, metadata=None):
    db.add(
        AuditRecord(
            id=new_id("aud"),
            org_id=org_id,
            actor_user_id=actor_user_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            metadata_json=metadata or {},
        )
    )
