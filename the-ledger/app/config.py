"""Runtime configuration. Everything is environment-driven so the same image
runs locally, in tests, and in Docker Compose."""
import os
import secrets

DEFAULT_DATABASE_URL = "sqlite:///./the_ledger.db"

# How long an issued session token stays valid.
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", str(12 * 3600)))

# Organizer-only reset key. If unset, reset is disabled.
ADMIN_KEY = os.environ.get("ADMIN_KEY")


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def flag() -> str:
    value = os.environ.get("FLAG")
    if value:
        return value
    # Random per process when not pinned by the operator.
    return "GCDxGLORY{the_ledger_" + secrets.token_hex(8) + "}"
