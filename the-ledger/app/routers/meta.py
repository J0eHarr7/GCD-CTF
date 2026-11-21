"""Service metadata: health and the API index.

There is deliberately no ``/openapi.json`` and no interactive docs — the
challenge is black-box only.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["meta"])


@router.get("/health")
def health():
    return {"status": "ok", "service": "the-ledger"}


@router.get("")
def index():
    return {
        "service": "the-ledger",
        "version": "v1",
        "authentication": "Bearer <session token> from POST /api/v1/auth",
        "resources": {
            "identity": ["/api/v1/auth", "/api/v1/sessions"],
            "projects": ["/api/v1/projects", "/api/v1/assessments"],
            "workflow": ["/api/v1/jobs", "/api/v1/events"],
            "audit": ["/api/v1/audit", "/api/v1/exports"],
            "reports": ["/api/v1/reports", "/api/v1/deliveries"],
        },
        "notes": [
            "Assessment lifecycle: DRAFT -> SUBMITTED -> APPROVED -> GENERATING -> READY.",
            "Errors share the shape {\"error\": {\"code\", \"message\", \"detail\"}}.",
        ],
    }
