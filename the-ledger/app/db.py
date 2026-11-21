"""Database engine and session management (SQLAlchemy 2.0, sync)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def init_engine(database_url: str):
    global _engine, _SessionLocal
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    _engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=True,
        future=True,
    )
    _SessionLocal = sessionmaker(
        bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    return _engine


def engine():
    if _engine is None:
        raise RuntimeError("database engine not initialised")
    return _engine


def SessionLocal():
    if _SessionLocal is None:
        raise RuntimeError("database session factory not initialised")
    return _SessionLocal()


def get_session():
    """FastAPI dependency: yield a session and close it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all():
    from . import models  # noqa: F401  (register mappings)

    Base.metadata.create_all(bind=engine())


def drop_all():
    from . import models  # noqa: F401

    Base.metadata.drop_all(bind=engine())
