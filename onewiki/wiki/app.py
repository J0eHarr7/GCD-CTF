"""
The One Wiki — public-facing Flask application.
Implements Stage 1 (recon / leaked artifacts), Stage 2 (BOLA on revisions),
and the entry points that feed Stage 3 (review bot) and Stage 4 (SSRF via
the citation importer). This is the ONLY service published to the host.
"""
import os
import re
import html
import hmac
import hashlib
import secrets
import requests
from flask import Flask, request, session, redirect, url_for, jsonify, render_template

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

FLAG_PREFIX = os.environ.get("FLAG_PREFIX", "LOTR")
REVIEW_SERVICE_URL = os.environ.get("REVIEW_SERVICE_URL", "http://review-service:5001")
IMPORT_SERVICE_URL = os.environ.get("IMPORT_SERVICE_URL", "http://import-service:5002")


def flag(stage, seed):
    """Deterministic, stage-scoped flag generator."""
    h = hashlib.sha256(f"{seed}-{stage}-onewiki".encode()).hexdigest()[:20]
    return f"{FLAG_PREFIX}{{{stage}_{h}}}"


FLAG_1 = flag("stage1_forgotten_age", "seven-gates-1007")
FLAG_2 = flag("stage2_palantir", "revision-moderation-policy")

# The remaining stage flags are produced identically in the downstream,
# internal-only services (review-service, conversion-worker and
# archive-service). They are mirrored here using the same deterministic
# generator so the final /flag gate can verify a complete run without ever
# calling those services. Each service reads FLAG_PREFIX from the environment,
# so this stays in sync even when the namespace is changed for a new event.
FLAG_3 = flag("stage3_whispering_archive", "preview-renderer-exfil")
FLAG_4 = flag("stage4_doors_of_durin", "ssrf-internal-pivot")
FLAG_5 = flag("stage5_mines_of_moria", "legacy-conversion-trust-flaw")
FLAG_6 = flag("stage6_black_gate", "confused-deputy-release")
FLAG_7 = flag("Fi1n4l_m0uNt_D00m", "Th3_0ne_R1nG_Th3_l4sT_4rcH1v3")

# Every stage flag, in the order they are earned across the seven stages.
ALL_STAGE_FLAGS = (FLAG_1, FLAG_2, FLAG_3, FLAG_4, FLAG_5, FLAG_6, FLAG_7)

# The "real" flag — revealed only once all seven stage flags are submitted.
REAL_FLAG = os.environ.get("REAL_FLAG", "GCDxGLORY{Th3_0ne_R1nG_Rul3_Th3m_4LL}")

# ---------------------------------------------------------------------------
# In-memory "database" — deterministic seed data, reset on container restart.
# ---------------------------------------------------------------------------

USERS = {
    "scholar1": {"password": "scholar123", "role": "scholar", "legacy_id": 2001},
    "archivist1": {"password": "archivist456", "role": "archivist", "legacy_id": 2002},
    # This account is never offered at registration and never linked from the
    # UI. Its existence is only confirmed by a restricted revision (Stage 2).
    "librarian-of-moria": {"password": "khazad-secret", "role": "reviewer", "legacy_id": 2003},
}

# slug -> page record. legacy_id is the "previous wiki" numeric identifier
# referenced by /legacy/export/<id> and by old revision metadata.
PAGES = {
    "Isildur": {
        "legacy_id": 1001,
        "title": "Isildur",
        "body": "Isildur, son of Elendil, took the One Ring from Sauron's hand "
                "at the slopes of Mount Doom but did not destroy it.",
        "current_revision": "rev-a3f9c2",
    },
    "Rivendell": {
        "legacy_id": 1002,
        "title": "Rivendell",
        "body": "Rivendell, or Imladris, is an Elven outpost hidden in a "
                "valley east of the Misty Mountains.",
        "current_revision": "rev-7c01de",
    },
    "Mithril": {
        "legacy_id": 1003,
        "title": "Mithril",
        "body": "A precious silver metal mined chiefly in Khazad-dum, prized "
                "for being both light and stronger than steel.",
        "current_revision": "rev-9b44aa",
    },
    # Deliberately NOT linked from the index. Only discoverable via the
    # legacy export format / sourcemap breadcrumbs (Stage 1).
    "The-Seven-Gates": {
        "legacy_id": 1007,
        "title": "The Seven Gates",
        "body": "A restricted record describing the sealed entrances once "
                "used by the White Council to move archive material without "
                "leaving a trace in the public revision log.\n\n"
                f"ARCHIVE NOTE: {FLAG_1}\n\n"
                "Cross-reference: revision access for restricted pages does "
                "not follow the same authorization path as page access. "
                "See the revision store directly.",
        "current_revision": "rev-d00rs1",
        "hidden_from_index": True,
    },
}

# revision_id -> revision record. Two revisions exist per page in most cases;
# the "restricted" one is what the public view never shows, and is the BOLA
# target for Stage 2: /api/revision/<id> checks only that the PAGE exists,
# not whether the REVISION itself is public.
REVISIONS = {
    "rev-a3f9c2": {
        "page": "Isildur", "status": "public", "author": "scholar1",
        "content": PAGES["Isildur"]["body"],
    },
    "rev-a3f9c1": {
        "page": "Isildur", "status": "restricted", "author": "archivist1",
        "content": (
            "DRAFT MODERATION POLICY (fragment)\n\n"
            "'...any revision flagged for review is queued for the "
            "automated preview renderer. The reviewing identity used "
            "internally is librarian-of-moria. This account holds elevated "
            "preview privileges and should never be exposed to the public "
            "revision log...'\n\n"
            f"{FLAG_2}\n\n"
            "Reviewer identity confirmed: librarian-of-moria"
        ),
    },
    "rev-7c01de": {
        "page": "Rivendell", "status": "public", "author": "scholar1",
        "content": PAGES["Rivendell"]["body"],
    },
    "rev-9b44aa": {
        "page": "Mithril", "status": "public", "author": "scholar1",
        "content": PAGES["Mithril"]["body"],
    },
    "rev-d00rs1": {
        "page": "The-Seven-Gates", "status": "restricted", "author": "archivist1",
        "content": PAGES["The-Seven-Gates"]["body"],
    },
}

# Pending edits queued for the review bot. rev_id -> {page, content, author, status}
PENDING_REVISIONS = {}

# Stage 3 evidence drop box — a generic, limited "receive whatever gets
# POSTed/GETted here" endpoint. This is the deliberately exposed evidence
# endpoint the review bot is told to call back to.
DROPBOX = {}


def render_public(markup: str) -> str:
    """
    The PUBLIC renderer. Escapes everything, then allows a small safe subset
    of custom Elvish markup. This is intentionally the 'safe' path —
    contrast with review-service's preview renderer (Stage 3).
    """
    escaped = html.escape(markup)
    # Safe subset: [[b:...]] -> <b>...</b>, nothing else is special here.
    escaped = re.sub(r"\[\[b:(.*?)\]\]", r"<b>\1</b>", escaped)
    return escaped


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def current_user():
    return session.get("user")


# ---------------------------------------------------------------------------
# Routes — core wiki
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    visible = {slug: p for slug, p in PAGES.items() if not p.get("hidden_from_index")}
    return render_template("index.html", pages=visible, user=current_user())


@app.route("/wiki/<slug>")
def view_page(slug):
    page = PAGES.get(slug)
    if not page:
        return "No such record in the archive.", 404
    rev = REVISIONS[page["current_revision"]]
    rendered = render_public(rev["content"])
    return render_template("page.html", page=page, slug=slug, rendered=rendered)


@app.route("/wiki/<slug>/history")
def page_history(slug):
    page = PAGES.get(slug)
    if not page:
        return "No such record in the archive.", 404
    # Only lists revision IDs tied to this page — does NOT reveal status,
    # which is part of what makes the BOLA in Stage 2 non-obvious: you still
    # have to go read each revision to learn one is 'restricted'.
    revs = [rid for rid, r in REVISIONS.items() if r["page"] == slug]
    return jsonify({"slug": slug, "legacy_id": page["legacy_id"], "revisions": revs})


@app.route("/api/revision/<rev_id>")
def api_revision(rev_id):
    """
    STAGE 2 — Broken Object-Level Authorization.

    Vulnerable check: we verify the PAGE referenced by the revision exists
    and is a real page, but never check whether THIS revision's status is
    'restricted' nor whether the caller holds the archivist/reviewer role.
    Page-level and revision-level authorization are two different code
    paths that quietly disagree with each other.
    """
    rev = REVISIONS.get(rev_id)
    if not rev:
        return jsonify({"error": "unknown revision"}), 404
    page = PAGES.get(rev["page"])
    if not page:
        return jsonify({"error": "orphaned revision"}), 404
    # <-- missing: `if rev["status"] == "restricted" and not is_archivist(): 403`
    return jsonify({
        "revision_id": rev_id,
        "page": rev["page"],
        "status": rev["status"],
        "author": rev["author"],
        "content": rev["content"],
    })


# ---------------------------------------------------------------------------
# Stage 1 — legacy artifacts
# ---------------------------------------------------------------------------

@app.route("/legacy/export/<int:legacy_id>")
def legacy_export(legacy_id):
    """Old export format from the previous wiki system, left reachable after
    the migration. Keys records by numeric legacy_id instead of slug."""
    for slug, page in PAGES.items():
        if page["legacy_id"] == legacy_id:
            return jsonify({
                "format": "onewiki-legacy-export-v1",
                "legacy_id": legacy_id,
                "slug": slug,
                "title": page["title"],
                "current_revision": page["current_revision"],
                "note": "Legacy export is read-only and scheduled for "
                        "deprecation. Slugs supersede legacy_id in v2.",
            })
    return jsonify({"error": "no such legacy_id"}), 404


@app.route("/old-docs/")
def old_docs_index():
    return (
        "<h3>Deprecated API documentation (v1)</h3>"
        "<ul>"
        "<li>GET /legacy/export/&lt;legacy_id&gt;</li>"
        "<li>GET /api/revision/&lt;revision_id&gt;</li>"
        "<li>See /static/js/app.js.map for the full v1 route table</li>"
        "</ul>"
        "<p><i>This directory should have been removed during migration.</i></p>"
    )


# ---------------------------------------------------------------------------
# Editing + Stage 3 hookup (review bot)
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p = request.form.get("username"), request.form.get("password")
        acct = USERS.get(u)
        if acct and acct["password"] == p:
            session["user"] = u
            return redirect(url_for("index"))
        return render_template("login.html", error="Invalid credentials"), 401
    return render_template("login.html", error=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/edit/<slug>", methods=["GET", "POST"])
def edit_page(slug):
    if not current_user():
        return redirect(url_for("login"))
    page = PAGES.get(slug)
    if not page:
        return "No such record in the archive.", 404

    if request.method == "POST":
        content = request.form.get("content", "")
        rev_id = "pend-" + secrets.token_hex(4)
        PENDING_REVISIONS[rev_id] = {
            "page": slug, "content": content, "author": current_user(),
            "status": "pending_review",
        }
        # Enqueue with the review service — this is what the privileged bot
        # will eventually render & visit (Stage 3).
        try:
            requests.post(
                f"{REVIEW_SERVICE_URL}/enqueue",
                json={"rev_id": rev_id, "page": slug, "content": content,
                      "author": current_user()},
                timeout=3,
            )
        except requests.RequestException:
            pass
        return render_template(
            "edit_submitted.html", slug=slug, rev_id=rev_id
        )

    return render_template("edit.html", page=page, slug=slug)


@app.route("/review-status/<rev_id>")
def review_status(rev_id):
    try:
        r = requests.get(f"{REVIEW_SERVICE_URL}/status/{rev_id}", timeout=3)
        return jsonify(r.json()), r.status_code
    except requests.RequestException:
        return jsonify({"error": "review service unreachable"}), 502


# ---------------------------------------------------------------------------
# Stage 4 hookup — citation importer (delegates the actual fetch to
# import-service, which is the only container with any path toward the
# internal archive network). The wiki itself never makes the outbound
# request, which is realistic: it's the IMPORT SERVICE'S network view that
# matters, not the wiki's.
# ---------------------------------------------------------------------------

@app.route("/import_citation", methods=["GET", "POST"])
def import_citation():
    if not current_user():
        return redirect(url_for("login"))
    result = None
    if request.method == "POST":
        target_url = request.form.get("url", "")
        try:
            r = requests.post(
                f"{IMPORT_SERVICE_URL}/fetch_citation",
                json={"url": target_url}, timeout=5,
            )
            result = r.json()
        except requests.RequestException as e:
            result = {"error": str(e)}
    return render_template("import_citation.html", result=result)


# ---------------------------------------------------------------------------
# Stage 3 evidence dropbox — a deliberately simple, limited "receive and
# later read back" endpoint. Review-service's bot is told (by a player's
# crafted markup) to forward evidence here; the player then reads it back.
# ---------------------------------------------------------------------------

@app.route("/dropbox/<box_id>", methods=["GET", "POST"])
def dropbox(box_id):
    if request.method == "POST":
        DROPBOX[box_id] = request.get_json(silent=True) or dict(request.args)
        return jsonify({"stored": True})
    data = request.args.to_dict()
    if data:
        # Also allow GET-based delivery (e.g. ?data=...), common for simple
        # callback simulations.
        DROPBOX.setdefault(box_id, {})
        DROPBOX[box_id].update(data)
    return jsonify(DROPBOX.get(box_id, {"note": "empty — nothing delivered yet"}))


# ---------------------------------------------------------------------------
# Final gate — submit all seven stage flags to reveal the real flag.
# ---------------------------------------------------------------------------

def _collect_submitted_flags():
    """Extract the seven flags from a JSON or form request.

    Accepted shapes (all just conveniences for the player):
      JSON   {"flags": ["f1", ..., "f7"]}
      JSON   {"flags": "f1\\nf2\\n..."}          (whitespace/comma separated)
      JSON   {"flag1": "f1", ..., "flag7": "f7"}
      form   flag1=...&flag2=...&...&flag7=...
      form   flags=f1&flags=f2&...                (repeated, or separated)
    """
    if request.is_json:
        data = request.get_json(silent=True) or {}
        flags = data.get("flags")
        if isinstance(flags, str):
            return [p for p in re.split(r"[\s,]+", flags.strip()) if p]
        if isinstance(flags, (list, tuple)):
            return [str(f).strip() for f in flags if str(f).strip()]
        named = [data.get(f"flag{i}") for i in range(1, 8)]
        if any(named):
            return [str(v).strip() for v in named if v not in (None, "")]
        return []

    raw = request.form.getlist("flags")
    if raw:
        collected = []
        for item in raw:
            collected.extend(p for p in re.split(r"[\s,]+", item.strip()) if p)
        return collected
    named = [request.form.get(f"flag{i}") for i in range(1, 8)]
    return [str(v).strip() for v in named if v not in (None, "")]


def _wants_json():
    """API clients get JSON; browser form submissions get the HTML template."""
    if request.is_json:
        return True
    if "format" in request.args:
        return request.args.get("format", "").lower() == "json"
    return (request.accept_mimetypes["application/json"] >
            request.accept_mimetypes["text/html"])


@app.route("/flag", methods=["GET", "POST"])
def final_flag():
    """Reveal REAL_FLAG only when all seven stage flags are submitted."""
    if request.method == "GET":
        if _wants_json():
            return jsonify({
                "status": "awaiting_submission",
                "instructions": (
                    "Submit all seven stage flags collected across the One Wiki "
                    "chain to reveal the real flag."
                ),
                "expected_count": len(ALL_STAGE_FLAGS),
                "usage": {
                    "json": {"flags": ["<stage 1 flag>", "...", "<stage 7 flag>"]},
                    "form": "flag1=...&flag2=...&...&flag7=...",
                },
            })
        return render_template("flag.html", user=current_user(),
                               result=None, submitted=[])

    submitted = _collect_submitted_flags()
    if len(submitted) != len(ALL_STAGE_FLAGS):
        result = {
            "ok": False,
            "error": "exactly seven flags are required",
            "expected_count": len(ALL_STAGE_FLAGS),
            "received_count": len(submitted),
        }
        status = 400
    else:
        # Order-insensitive, but every flag must be present exactly once.
        remaining = list(ALL_STAGE_FLAGS)
        result = None
        status = 200
        for candidate in submitted:
            matched = None
            for expected in remaining:
                # Compare as bytes so non-ASCII input cannot raise a TypeError.
                if hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8")):
                    matched = expected
                    break
            if matched is None:
                result = {"ok": False, "error": "one or more submitted flags are incorrect"}
                status = 403
                break
            remaining.remove(matched)
        if result is None:
            result = {
                "ok": True,
                "status": "correct",
                "message": "All seven flags verified. The One Ring is yours.",
                "flag": REAL_FLAG,
            }

    if _wants_json():
        payload = dict(result)
        payload.pop("ok", None)
        return jsonify(payload), status
    return render_template("flag.html", user=current_user(),
                           result=result, submitted=submitted), status


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "wiki"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
