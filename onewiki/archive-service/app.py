"""
Archive Service — the hidden, most restricted service in the chain. Never
published to the host; reachable only via the network segment pivoted into
through Stage 4's SSRF. Holds the synthetic service-assertion trust model
and the final record, The-Last-Archive.

This is where the challenge's single underlying architectural mistake pays
off: every layer above this one trusted PROVENANCE METADATA (a self-reported
flag, an internal service name, a signed-looking assertion) more than it
verified WHO was actually asking and WHAT they were actually asking to do.
Archive-service itself repeats the mistake one layer deeper: it validates
that an assertion is signed and that the service/role are on an allowlist,
but never binds the assertion to the specific operation it was issued for,
and never consistently checks record ownership.
"""
import os
import json
import base64
import hashlib
import hmac
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

FLAG_PREFIX = os.environ.get("FLAG_PREFIX", "LOTR")
ARCHIVE_SIGNING_SECRET = os.environ.get("ARCHIVE_SIGNING_SECRET", "change-me")


def flag(stage, seed):
    h = hashlib.sha256(f"{seed}-{stage}-onewiki".encode()).hexdigest()[:20]
    return f"{FLAG_PREFIX}{{{stage}_{h}}}"


FLAG_4 = flag("stage4_doors_of_durin", "ssrf-internal-pivot")
FLAG_6 = flag("stage6_black_gate", "confused-deputy-release")
FINAL_FLAG = flag("Fi1n4l_m0uNt_D00m","Th3_0ne_R1nG_Th3_l4sT_4rcH1v3")

EVIDENCE_TOKEN = hashlib.sha256(b"palantir-renderer-evidence-token").hexdigest()[:24]

# service/role combinations archive-service is willing to trust an
# assertion from at all. Note: this allowlist is the ONLY gate — nothing
# downstream checks whether "worker" should be allowed to do "release".
ALLOWED_SERVICES = {"conversion-worker"}
ALLOWED_ROLES = {"worker", "archivist"}

# record_id -> owner_legacy_id (None = never properly re-archived after the
# migration; the field is simply missing, not "public").
RECORDS = {
    "The-Last-Archive": {"owner_legacy_id": None, "flag": FINAL_FLAG},
}

ISSUED_RELEASE_TOKENS = {}  # for /healthz introspection only, not security


def b64_decode_token(token: str):
    try:
        raw = base64.urlsafe_b64decode(token.encode())
        obj = json.loads(raw)
        assertion = obj["assertion"]
        signature = obj["signature"]
    except Exception:
        return None, None
    expected = hmac.new(
        ARCHIVE_SIGNING_SECRET.encode(),
        json.dumps(assertion, sort_keys=True).encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None, None
    return assertion, signature


def sign(obj: dict) -> str:
    payload = json.dumps(obj, sort_keys=True).encode()
    sig = hmac.new(ARCHIVE_SIGNING_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(json.dumps({"assertion": obj, "signature": sig}).encode()).decode()


# ---------------------------------------------------------------------------
# Stage 4 landing points — reached only via the import-service SSRF pivot.
# ---------------------------------------------------------------------------

@app.route("/internal/manifest-hint")
def manifest_hint():
    return jsonify({
        "flag": FLAG_4,
        "service": "archive-service",
        "note": "You've reached the restricted archive segment. The internal "
                "service name alone only gets you this far — deeper "
                "endpoints require evidence gathered from the review "
                "workflow (see /internal/full-manifest).",
    })


@app.route("/internal/full-manifest")
def full_manifest():
    token = request.args.get("evidence_token", "")
    if token != EVIDENCE_TOKEN:
        return jsonify({"error": "missing or invalid evidence_token"}), 403
    return jsonify({
        "restricted_service_id": "archive-service",
        "sample_worker_request": {
            "note": "illustrative only — not a valid signature",
            "assertion": {
                "service": "conversion-worker", "role": "worker",
                "audience": "archive-service", "issued_for": "convert",
            },
            "signature": "0000000000000000000000000000000000000000000000000000000000000000",
        },
        "hint": "The conversion worker issues real, validly signed "
                "assertions like this when it trusts a submission's "
                "self-reported provenance. See its /diagnostics endpoint.",
    })


# ---------------------------------------------------------------------------
# Stage 6 — confused deputy / broken service authorization
# ---------------------------------------------------------------------------

@app.route("/archive/operation", methods=["GET", "POST"])
def archive_operation():
    if request.method == "GET":
        assertion_token = request.args.get("assertion_token", "")
        op = request.args.get("op", "")
        record_id = request.args.get("record_id", "")
        requested_by = request.args.get("requested_by")
    else:
        data = request.get_json(force=True, silent=True) or {}
        assertion_token = data.get("assertion_token", "")
        op = data.get("op", "")
        record_id = data.get("record_id", "")
        requested_by = data.get("requested_by")

    assertion, _ = b64_decode_token(assertion_token)
    if not assertion:
        return jsonify({"error": "invalid or unsigned assertion"}), 403
    if assertion.get("service") not in ALLOWED_SERVICES:
        return jsonify({"error": "service not permitted to call the archive"}), 403
    if assertion.get("role") not in ALLOWED_ROLES:
        return jsonify({"error": "role not permitted"}), 403
    # VULNERABLE: assertion["issued_for"] (== "convert") is never compared
    # against the requested `op` (== "release"). Audience is checked for
    # presence but not for operation-scoping. Any assertion that passes the
    # service/role allowlist can request ANY operation.

    if op == "convert":
        return jsonify({"op": "convert", "accepted": True,
                         "note": "no-op acknowledgement"})

    if op == "release":
        if record_id not in RECORDS:
            return jsonify({"error": "unknown record_id"}), 404
        release_obj = {
            "record_id": record_id,
            "owner": requested_by,
            "op": "release",
            "issued_at": int(time.time()),
        }
        release_token = sign(release_obj)
        ISSUED_RELEASE_TOKENS[record_id] = release_token
        return jsonify({
            "flag": FLAG_6,
            "release_token": release_token,
            "note": "Release record issued. A worker-role assertion should "
                    "never have been sufficient for a release operation — "
                    "the audience/operation binding is missing. Use this "
                    "release_token against /archive/record/<record_id>.",
        })

    return jsonify({"error": f"unknown op: {op}"}), 400


# ---------------------------------------------------------------------------
# Stage 7 — final record, gated by ownership logic that disagrees with the
# rest of the system.
# ---------------------------------------------------------------------------

@app.route("/archive/record/<record_id>")
def get_record(record_id):
    release_token = request.args.get("release_token", "")
    record = RECORDS.get(record_id)
    if not record:
        return jsonify({"error": "unknown record"}), 404

    release_obj, _ = b64_decode_token(release_token)
    if not release_obj:
        return jsonify({"error": "missing or invalid release_token"}), 403
    if release_obj.get("record_id") != record_id or release_obj.get("op") != "release":
        return jsonify({"error": "release_token not valid for this record/operation"}), 403

    owner_legacy_id = record.get("owner_legacy_id")
    token_owner = release_obj.get("owner")
    if owner_legacy_id is not None:
        # Normal path: ownership must match.
        if str(token_owner) != str(owner_legacy_id):
            return jsonify({"error": "release token owner does not match record owner"}), 403
    # VULNERABLE: when owner_legacy_id is None (this record was never
    # properly re-archived after migration — see the briefing), ownership
    # is simply never checked. Multiple subsystems disagree about who
    # should own an orphaned record, and the archive defaults to trusting
    # whatever the release token claims — or claims nothing at all.

    return jsonify({
        "record_id": record_id,
        "flag": record["flag"],
        "narrative": "The One Ring was never destroyed. It was archived.",
    })


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "archive-service"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5004, debug=False)
