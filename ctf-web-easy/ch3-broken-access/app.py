import os
import secrets
from flask import Flask, request, jsonify, session

app = Flask(__name__)
# NOTE: with several gunicorn workers a random per-process key would break sessions,
# so derive it from the environment (or a fixed fallback for the CTF).
app.secret_key = os.environ.get("SECRET_KEY", "ctf-notekeeper-session-key-not-the-goal")
FLAG = os.environ.get("FLAG", "CTF{1d0r_4nd_br0k3n_4cc3ss_c0ntr0l}")

# id -> user. Admin password is random and unknown: players must NOT log in as admin.
USERS = {
    1: {"username": "admin", "password": os.environ.get("ADMIN_PASSWORD", secrets.token_hex(16)), "role": "admin"},
    2: {"username": "alice", "password": "alice123", "role": "user"},
    3: {"username": "bob", "password": "bob123", "role": "user"},
}

# id -> note (owner = user id)
NOTES = {
    1: {"owner": 1, "title": "Admin secret", "body": f"Do not share: {FLAG}"},
    2: {"owner": 2, "title": "Shopping list", "body": "Milk, eggs, coffee"},
    3: {"owner": 3, "title": "Todo", "body": "Finish the CTF challenge"},
    4: {"owner": 2, "title": "Reminder", "body": "Notes are numbered. Mine start at 2."},
}

INDEX = """<!doctype html>
<html><head><title>NoteKeeper</title>
<style>body{font-family:monospace;background:#0d1117;color:#c9d1d9;max-width:660px;margin:60px auto}
code{background:#161b22;padding:2px 6px;border-radius:4px}</style></head>
<body>
<h1>📝 NoteKeeper</h1>
<p>Test account: <code>alice / alice123</code></p>
<ul>
<li><code>/api/login</code></li>
<li><code>/api/me</code></li>
<li><code>/api/notes</code></li>
<li><code>/api/notes/&lt;id&gt;</code></li>
<li><code>/api/users/&lt;id&gt;</code></li>
</ul>
</body></html>"""


def current_user():
    uid = session.get("uid")
    return (uid, USERS.get(uid)) if uid else (None, None)


@app.route("/")
def index():
    return INDEX


@app.route("/api/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    for uid, u in USERS.items():
        if u["username"] == body.get("username") and u["password"] == body.get("password"):
            session["uid"] = uid
            return jsonify(message="Logged in", id=uid, username=u["username"])
    return jsonify(error="Bad credentials"), 401


@app.route("/api/me")
def me():
    uid, u = current_user()
    if not u:
        return jsonify(error="Login required"), 401
    return jsonify(id=uid, username=u["username"], role=u["role"])


@app.route("/api/notes")
def list_notes():
    uid, u = current_user()
    if not u:
        return jsonify(error="Login required"), 401
    mine = [{"id": nid, "title": n["title"]} for nid, n in NOTES.items() if n["owner"] == uid]
    return jsonify(notes=mine)


@app.route("/api/notes/<int:note_id>")
def get_note(note_id):
    uid, u = current_user()
    if not u:
        return jsonify(error="Login required"), 401
    note = NOTES.get(note_id)
    if not note:
        return jsonify(error="Note not found"), 404
    # VULNERABILITY: authenticated, but no ownership check (IDOR / broken access control)
    # Fix: if note["owner"] != uid and u["role"] != "admin": return 403
    return jsonify(id=note_id, owner=note["owner"], title=note["title"], body=note["body"])


@app.route("/api/users/<int:user_id>")
def get_user(user_id):
    uid, u = current_user()
    if not u:
        return jsonify(error="Login required"), 401
    target = USERS.get(user_id)
    if not target:
        return jsonify(error="User not found"), 404
    return jsonify(id=user_id, username=target["username"], role=target["role"])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
