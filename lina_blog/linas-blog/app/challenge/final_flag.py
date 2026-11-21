"""
One flag, generated randomly per deployment, held only server-side in
process memory (and optionally overridable via the FLAG environment
variable for scored deployments). It is never returned by any endpoint
except as the rendered body of the protected final article, and only
once a valid entitlement row exists for the requesting user.
"""
import os
import secrets

_FLAG = None


def init_flag(app):
    global _FLAG
    env_flag = os.environ.get("FLAG")
    _FLAG = env_flag if env_flag else f"FLAG{{{secrets.token_hex(16)}}}"
    # Stored on the app config too, but nothing ever serializes app.config
    # to a client — kept here as the single source of truth.
    app.config["CHALLENGE_FLAG"] = _FLAG


def get_flag():
    return _FLAG
