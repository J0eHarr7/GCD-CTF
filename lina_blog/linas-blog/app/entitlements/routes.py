from flask import Blueprint, jsonify, g

bp = Blueprint("entitlements", __name__, url_prefix="/api")


def grant_entitlement(db, user_id, article_id, order_id):
    """Grant access to an article on the strength of a 'paid' order.

    This is intentionally the weak link: it trusts that orders.status ==
    'paid' means a legitimate, full-price payment was made. It does not
    recompute the article's true price with correct arithmetic and compare
    it against amount_charged_cents, and it does not look at whether the
    charged amount makes any business sense (e.g. zero or negative).
    """
    order = db.execute(
        "SELECT * FROM orders WHERE id = ? AND user_id = ? AND article_id = ?",
        (order_id, user_id, article_id),
    ).fetchone()

    if order is None or order["status"] != "paid":
        return False

    db.execute(
        """INSERT OR IGNORE INTO entitlements (user_id, article_id, order_id)
           VALUES (?, ?, ?)""",
        (user_id, article_id, order_id),
    )
    return True


@bp.route("/library")
def library():
    if g.user is None:
        return jsonify({"error": "Login required."}), 401

    from app.db import get_db

    db = get_db()
    rows = db.execute(
        """SELECT a.slug, a.title, a.category, e.granted_at
           FROM entitlements e
           JOIN articles a ON a.id = e.article_id
           WHERE e.user_id = ?
           ORDER BY e.granted_at DESC""",
        (g.user["id"],),
    ).fetchall()

    return jsonify(
        {
            "library": [
                {"slug": r["slug"], "title": r["title"], "category": r["category"], "granted_at": r["granted_at"]}
                for r in rows
            ]
        }
    )
