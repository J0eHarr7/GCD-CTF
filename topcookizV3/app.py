import sqlite3
import uuid
import os
from flask import Flask, request, redirect, render_template, g, make_response, jsonify

app = Flask(__name__)
DB_PATH = os.path.join(os.path.dirname(__file__), "topcookiz.db")
FLAG = os.environ.get("FLAG", "TopCookiz{d3m0_fl4g_s3t_via_env}")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        db = g._db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()


def init_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'employee',
            auth_token TEXT
        );

        CREATE TABLE batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cookie_type TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            owner_id INTEGER NOT NULL
        );
        """
    )
    db.execute(
        "INSERT INTO users (username, password, role, auth_token) VALUES (?,?,?,?)",
        ("J0eHarr7", "C00ki3M4st3r_3999!", "employee", None),
    )
    db.execute(
        "INSERT INTO users (username, password, role, auth_token) VALUES (?,?,?,?)",
        ("stock_bot", "automatedAccount#1", "employee", None),
    )
    db.executemany(
        "INSERT INTO batches (cookie_type, quantity, owner_id) VALUES (?,?,?)",
        [
            ("Chocolate Chunk", 500, 2),
            ("Oatmeal Raisin", 320, 2),
            ("Matcha White Choc", 150, 3),
        ],
    )
    db.commit()
    db.close()

def get_user_from_cookie():
    token = request.cookies.get("auth_token")
    if not token:
        return None
    db = get_db()
    query = f"SELECT * FROM users WHERE auth_token = '{token}'"
    try:
        cur = db.execute(query)
        row = cur.fetchone()
        return row
    except sqlite3.Error:
        return None


@app.route("/")
def index():
    user = get_user_from_cookie()
    return render_template("index.html", user=user)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", error=None)

    username = request.form.get("username", "")
    password = request.form.get("password", "")
    db = get_db()
    row = db.execute(
        "SELECT * FROM users WHERE username = ? AND password = ?",
        (username, password),
    ).fetchone()

    if row is None:
        return render_template("login.html", error="Invalid credentials")

    token = str(uuid.uuid4())
    db.execute("UPDATE users SET auth_token = ? WHERE id = ?", (token, row["id"]))
    db.commit()

    resp = make_response(redirect("/stock"))
    resp.set_cookie("auth_token", token, httponly=False)
    return resp


@app.route("/logout")
def logout():
    resp = make_response(redirect("/"))
    resp.delete_cookie("auth_token")
    return resp


@app.route("/stock")
def stock():
    user = get_user_from_cookie()
    if not user:
        return redirect("/login")
    db = get_db()
    batches = db.execute("SELECT * FROM batches").fetchall()
    return render_template("stock.html", user=user, batches=batches)

@app.route("/api/profile", methods=["PATCH"])
def update_profile():
    user = get_user_from_cookie()
    if not user:
        return jsonify({"error": "unauthenticated"}), 401

    data = request.get_json(silent=True) or {}
    allowed_columns = {"username", "password", "role"}
    updates = {k: v for k, v in data.items() if k in allowed_columns}

    if not updates:
        return jsonify({"error": "no valid fields"}), 400

    db = get_db()
    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values()) + [user["id"]]
    db.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values) 
    db.commit()

    return jsonify({"status": "ok", "updated": list(updates.keys())})


@app.route("/admin/dashboard")
def admin_dashboard():
    user = get_user_from_cookie()
    if not user:
        return redirect("/login")
    if user["role"] != "admin":
        return render_template("forbidden.html"), 403
    return render_template("admin.html", flag=FLAG, user=user)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
