"""
Conversion Worker — converts legacy archival packages into the current wiki
format. Internal-only service, reachable only via the restricted network
segment discovered through Stage 4's SSRF.

STAGE 5 vulnerability: the VALIDATION stage and the CONVERSION stage
disagree about what counts as "trusted". Validation only checks that the
manifest is well-formed; conversion then trusts a self-reported
`source_verified` flag with no cryptographic backing to decide whether to
hand back a signed worker assertion. This mirrors the whole challenge's
underlying flaw: provenance metadata is trusted over identity.
"""
import os
import json
import base64
import hashlib
import hmac
from flask import Flask, request, jsonify

app = Flask(__name__)

FLAG_PREFIX = os.environ.get("FLAG_PREFIX", "LOTR")
ARCHIVE_SIGNING_SECRET = os.environ.get("ARCHIVE_SIGNING_SECRET", "change-me")


def flag(stage, seed):
    h = hashlib.sha256(f"{seed}-{stage}-onewiki".encode()).hexdigest()[:20]
    return f"{FLAG_PREFIX}{{{stage}_{h}}}"


FLAG_5 = flag("stage5_mines_of_moria", "legacy-conversion-trust-flaw")

SUPPORTED_FORMATS = {"legacy-v1"}


def sign_assertion(assertion: dict) -> str:
    payload = json.dumps(assertion, sort_keys=True).encode()
    sig = hmac.new(ARCHIVE_SIGNING_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    token = {"assertion": assertion, "signature": sig}
    return base64.urlsafe_b64encode(json.dumps(token).encode()).decode()


@app.route("/diagnostics")
def diagnostics():
    """
    Diagnostic output, intentionally left on in the challenge build. Reveals
    that `source_verified` is the field conversion trusts, and that a
    successful trusted conversion can include a worker service assertion —
    without saying outright that the field is unauthenticated.
    """
    return jsonify({
        "service": "conversion-worker",
        "supported_formats": sorted(SUPPORTED_FORMATS),
        "manifest_fields": ["legacy_id", "format", "source_verified", "content"],
        "conversion_options": {
            "include_worker_token": (
                "Included automatically when a submitted manifest's "
                "'source_verified' field is true and format is 'legacy-v1'. "
                "Used by internal batch jobs to chain into the archive "
                "service without re-authenticating."
            ),
        },
        "note": "Validation checks manifest shape. Conversion checks trust "
                "flags. These are two different code paths.",
    })


@app.route("/convert", methods=["POST", "GET"])
def convert():
    """
    Accepts POST JSON ({"manifest": {...}, "content": "..."}) for normal
    service-to-service calls, AND GET with flat query params — this
    service is only ever reached through the import-service's citation
    fetcher (a GET-only pivot), so a query-param mode is kept for that path.
    """
    if request.method == "GET":
        manifest = {
            "legacy_id": request.args.get("legacy_id"),
            "format": request.args.get("format"),
            "source_verified": request.args.get("source_verified") == "true",
        }
        content = request.args.get("content", "")
    else:
        data = request.get_json(force=True, silent=True) or {}
        manifest = data.get("manifest", {})
        content = data.get("content", "")

    fmt = manifest.get("format")
    if fmt not in SUPPORTED_FORMATS:
        return jsonify({"error": f"unsupported format: {fmt}"}), 400

    legacy_id = manifest.get("legacy_id")
    source_verified = manifest.get("source_verified", False)

    converted = {
        "converted_content": content.strip(),
        "format": "current-v2",
        "legacy_id": legacy_id,
    }

    if source_verified is True:
        # VULNERABLE: trusts a client-supplied boolean with no signature or
        # cross-check against any real provenance record.
        assertion = {
            "service": "conversion-worker",
            "role": "worker",
            "audience": "archive-service",
            "issued_for": "convert",
            "legacy_id": legacy_id,
        }
        converted["worker_token"] = sign_assertion(assertion)
        converted["flag"] = FLAG_5
        converted["restricted_service_id"] = "archive-service"
        converted["note"] = (
            "Trusted legacy source confirmed — issuing worker assertion for "
            "chained archive operations. This assertion authorizes the "
            "'convert' operation only."
        )

    return jsonify(converted)


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "conversion-worker"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003, debug=False)
