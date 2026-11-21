import os
import datetime
import jwt
from flask import Flask, request, jsonify

app = Flask(__name__)
FLAG = os.environ.get("FLAG", "CTF{w34k_jwt_s3cr3ts_g3t_cr4ck3d}")
# Intentionally weak secret, present in wordlist.txt
JWT_SECRET = os.environ.get("JWT_SECRET", "sunshine")

USERS = {"guest": "guest"}

INDEX = """<!doctype html>
<html><head><title>TokenCorp</title>
<style>body{font-family:monospace;background:#0d1117;color:#c9d1d9;max-width:640px;margin:60px auto}
code{background:#161b22;padding:2px 6px;border-radius:4px}</style></head>
<body>
<h1>🪙 TokenCorp Portal</h1>
<p>Guest credentials: <code>guest / guest</code></p>
<ul>
<li><code>POST /login</code> &mdash; JSON <code>{"username":"..","password":".."}</code></li>
<li><code>GET /me</code> &mdash; header <code>Authorization: Bearer &lt;token&gt;</code></li>
<li><code>GET /admin</code> &mdash; admins only</li>
</ul>
<p>Wordlist hint: <a href="/wordlist.txt">/wordlist.txt</a></p>
</body></html>"""


def make_token(username, role):
    payload = {
        "sub": username,
        "role": role,
        "iat": datetime.datetime.now(datetime.timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def read_token():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None, (jsonify(error="Missing Bearer token"), 401)
    try:
        # Only HS256 accepted: the weakness is the secret, not the algorithm
        data = jwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"])
        return data, None
    except jwt.PyJWTError as e:
        return None, (jsonify(error=f"Invalid token: {e}"), 401)


@app.route("/")
def index():
    return INDEX


@app.route("/wordlist.txt")
def wordlist():
    with open(os.path.join(os.path.dirname(__file__), "wordlist.txt")) as f:
        return f.read(), 200, {"Content-Type": "text/plain"}


@app.route("/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    u, p = body.get("username"), body.get("password")
    if u is not None and USERS.get(u) == p:
        return jsonify(token=make_token(u, "user"))
    return jsonify(error="Bad credentials"), 401


@app.route("/me")
def me():
    data, err = read_token()
    if err:
        return err
    return jsonify(username=data["sub"], role=data["role"])


@app.route("/admin")
def admin():
    data, err = read_token()
    if err:
        return err
    if data.get("role") != "admin":
        return jsonify(error="Admins only", your_role=data.get("role")), 403
    return jsonify(message=f"Welcome, {data['sub']}", flag=FLAG)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
