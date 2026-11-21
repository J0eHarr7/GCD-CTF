"""The Ledger — application factory.

One FastAPI application models several logical services (identity, projects,
workflow, audit, reports). They share a database but keep distinct trust
boundaries: the workflow service emits events that the report service trusts,
and the report service caches access decisions that nothing invalidates.
"""
from fastapi import FastAPI

from . import config
from .db import SessionLocal, create_all, init_engine
from .errors import install_handlers
from .models import Organization


def create_app(database_url: str | None = None) -> FastAPI:
    init_engine(database_url or config.database_url())
    create_all()

    db = SessionLocal()
    try:
        if db.query(Organization).count() == 0:
            from .seed import seed

            seed(db)
    finally:
        db.close()

    app = FastAPI(
        title="The Ledger API",
        version="v1",
        # Black-box challenge: no schema dump, no interactive docs.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    install_handlers(app)

    from .routers import admin, audit, identity, meta, projects, reports, workflow

    app.include_router(meta.router)
    app.include_router(identity.router)
    app.include_router(projects.router)
    app.include_router(workflow.router)
    app.include_router(audit.router)
    app.include_router(reports.router)
    app.include_router(admin.router)

    return app
