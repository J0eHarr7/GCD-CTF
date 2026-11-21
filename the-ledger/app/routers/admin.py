"""Organizer-only administration. Disabled unless ``ADMIN_KEY`` is set."""
from fastapi import APIRouter, Header

from .. import config
from ..errors import ApiError

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/reset")
def reset(x_admin_key: str | None = Header(default=None)):
    if not config.ADMIN_KEY:
        # No key configured: the endpoint does not exist.
        raise ApiError(404, "not_found", "no such resource")
    if x_admin_key != config.ADMIN_KEY:
        raise ApiError(403, "forbidden", "invalid admin key")

    from ..seed import reset_all

    reset_all()
    return {"reset": True, "service": "the-ledger"}
