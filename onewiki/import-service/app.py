"""
Import Service — fetches citations from "another archive" on behalf of the
wiki's editor feature. Internal-only service, but it is the ONLY container
with any network path toward the restricted archive segment.

STAGE 4 vulnerability (SSRF): URL validation uses a denylist of obvious
loopback/metadata strings, never an allowlist of the intended public lore
domain, and never re-validates the final destination after the fetch. Since
this service's /etc/hosts resolves internal docker service names, a player
who gets the wiki to call this endpoint with an internal hostname pivots
straight into the restricted network segment.
"""
import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

DENYLIST_SUBSTRINGS = ["127.0.0.1", "localhost", "0.0.0.0", "169.254.169.254", "::1"]


def is_denied(url: str) -> bool:
    lowered = url.lower()
    return any(bad in lowered for bad in DENYLIST_SUBSTRINGS)


@app.route("/fetch_citation", methods=["POST"])
def fetch_citation():
    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url", "")
    if not url:
        return jsonify({"error": "url required"}), 400
    if is_denied(url):
        return jsonify({"error": "destination blocked by policy"}), 403

    try:
        resp = requests.get(url, timeout=5, allow_redirects=True)
    except requests.RequestException as e:
        return jsonify({"error": f"fetch failed: {e}"}), 502

    content_type = resp.headers.get("Content-Type", "")
    body = resp.text[:4000]
    parsed = None
    if "json" in content_type:
        try:
            parsed = resp.json()
        except ValueError:
            parsed = None

    return jsonify({
        "requested_url": url,
        "status_code": resp.status_code,
        "content_type": content_type,
        "parsed": parsed,
        "raw_excerpt": None if parsed else body,
        "note": "citation importer: title/summary extraction applied when "
                "the source returns structured lore-database JSON.",
    })


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "import-service"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=False)
