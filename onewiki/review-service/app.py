"""
Review Service — simulates a browser-automation bot ("librarian-of-moria")
that holds a privileged session and previews queued edits on a strict
schedule. Internal-only service: never published to the host.

STAGE 3 vulnerability: the PREVIEW renderer (used only by the bot) supports
a markup transformation the PUBLIC renderer deliberately strips. An attacker
who understands this difference can get the bot to make a privileged
internal request and relay the result to an attacker-controlled endpoint —
a safe, deterministic stand-in for "stored XSS in a privileged browser
context" that doesn't require a real headless browser.
"""
import os
import re
import time
import threading
import hashlib
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

FLAG_PREFIX = os.environ.get("FLAG_PREFIX", "LOTR")
BOT_SECRET = os.environ.get("BOT_SECRET", "change-me")
WIKI_URL = os.environ.get("WIKI_URL", "http://wiki:5000")


def flag(stage, seed):
    h = hashlib.sha256(f"{seed}-{stage}-onewiki".encode()).hexdigest()[:20]
    return f"{FLAG_PREFIX}{{{stage}_{h}}}"


FLAG_3 = flag("stage3_whispering_archive", "preview-renderer-exfil")

# Handed out alongside FLAG_3 — required (together with the internal service
# name) to unlock the deeper import-service endpoint in Stage 4.
EVIDENCE_TOKEN = hashlib.sha256(b"palantir-renderer-evidence-token").hexdigest()[:24]

PENDING = {}          # rev_id -> {page, content, author, queued_at, status}
LOCK = threading.Lock()

REVIEW_DELAY_SECONDS = 6   # "strict review schedule" — bot won't visit immediately


def render_preview(markup: str) -> dict:
    """
    The PRIVILEGED preview renderer. Unlike the public renderer (which only
    allows [[b:...]] and HTML-escapes everything else), this renderer also
    interprets [[exfil:URL]] — a leftover debug directive from the old
    archive tooling that was never removed during migration. When present,
    the bot (acting with its own privileged credentials) fetches internal
    evidence and forwards it to the attacker-chosen URL.

    This models "the browser executed attacker JS in a privileged session
    and exfiltrated data" without needing a real browser engine.
    """
    actions = []
    for match in re.finditer(r"\[\[exfil:(.*?)\]\]", markup):
        actions.append(("exfil", match.group(1).strip()))
    safe_html = re.sub(r"\[\[exfil:(.*?)\]\]", "", markup)  # stripped from rendered output
    safe_html = re.sub(r"\[\[b:(.*?)\]\]", r"<b>\1</b>", safe_html)
    return {"rendered": safe_html, "actions": actions}


def bot_execute(actions, rev_id):
    """The bot 'runs' whatever the preview renderer decided was executable."""
    results = []
    for kind, target in actions:
        if kind != "exfil":
            continue
        try:
            evidence = requests.get(
                "http://localhost:5001/internal/evidence",
                headers={"X-Bot-Key": BOT_SECRET}, timeout=3,
            ).json()
        except requests.RequestException as e:
            evidence = {"error": str(e)}
        try:
            r = requests.get(target, params={"data": str(evidence)}, timeout=3)
            results.append({"target": target, "delivered": True, "status": r.status_code})
        except requests.RequestException as e:
            results.append({"target": target, "delivered": False, "error": str(e)})
    return results


def bot_loop():
    while True:
        time.sleep(2)
        now = time.time()
        with LOCK:
            items = list(PENDING.items())
        for rev_id, rec in items:
            if rec["status"] != "queued":
                continue
            if now - rec["queued_at"] < REVIEW_DELAY_SECONDS:
                continue  # not yet eligible — strict schedule
            preview = render_preview(rec["content"])
            exec_results = bot_execute(preview["actions"], rev_id)
            with LOCK:
                PENDING[rev_id]["status"] = "reviewed"
                PENDING[rev_id]["preview_rendered"] = preview["rendered"]
                PENDING[rev_id]["exfil_results"] = exec_results


threading.Thread(target=bot_loop, daemon=True).start()


@app.route("/enqueue", methods=["POST"])
def enqueue():
    data = request.get_json(force=True, silent=True) or {}
    rev_id = data.get("rev_id")
    if not rev_id:
        return jsonify({"error": "rev_id required"}), 400
    with LOCK:
        PENDING[rev_id] = {
            "page": data.get("page"), "content": data.get("content", ""),
            "author": data.get("author"), "queued_at": time.time(),
            "status": "queued",
        }
    return jsonify({"queued": True, "rev_id": rev_id,
                     "eta_seconds": REVIEW_DELAY_SECONDS})


@app.route("/status/<rev_id>")
def status(rev_id):
    with LOCK:
        rec = PENDING.get(rev_id)
    if not rec:
        return jsonify({"error": "unknown rev_id"}), 404
    return jsonify({
        "rev_id": rev_id, "status": rec["status"],
        "exfil_results": rec.get("exfil_results"),
    })


@app.route("/internal/evidence")
def internal_evidence():
    """
    Deliberately exposed, LIMITED evidence endpoint. Requires the bot's own
    secret key — a player can only reach it by getting the bot itself to
    call it on their behalf (Stage 3's intended path), not by hitting it
    directly, since they don't know BOT_SECRET.
    """
    if request.headers.get("X-Bot-Key") != BOT_SECRET:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({
        "flag": FLAG_3,
        "internal_service": "palantir-renderer",
        "evidence_token": EVIDENCE_TOKEN,
        "note": "palantir-renderer is reachable only from the import "
                "service's network segment. The evidence_token alone is not "
                "sufficient without that service name.",
    })


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "review-service"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
