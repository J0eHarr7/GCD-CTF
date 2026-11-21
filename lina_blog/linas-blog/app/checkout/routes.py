import secrets

from flask import Blueprint, request, jsonify, session, g

from app.db import get_db
from app.billing.legacy_arithmetic import compute_line_total

bp = Blueprint("checkout", __name__, url_prefix="/api/checkout")

# A generous-looking but ultimately irrelevant sanity cap. It exists so the
# API "looks" validated, but it is far above the quantity actually needed
# to trip the legacy billing overflow, so it does not meaningfully protect
# anything.
MAX_QUANTITY = 1_000_000


def _require_login():
    return g.get("user") if hasattr(g, "get") else None


@bp.route("/quote", methods=["POST"])
def quote():
    if g.user is None:
        return jsonify({"error": "You must be logged in to request a quote."}), 401

    data = request.get_json(silent=True) or {}
    article_id = data.get("article_id")
    quantity = data.get("quantity")

    if not isinstance(article_id, int):
        return jsonify({"error": "article_id must be an integer."}), 400
    if not isinstance(quantity, int) or quantity <= 0:
        return jsonify({"error": "quantity must be a positive integer."}), 400
    if quantity > MAX_QUANTITY:
        return jsonify({"error": f"quantity may not exceed {MAX_QUANTITY}."}), 400

    db = get_db()
    article = db.execute(
        "SELECT * FROM articles WHERE id = ? AND access = 'premium'",
        (article_id,),
    ).fetchone()
    if article is None:
        return jsonify({"error": "Unknown premium article."}), 404

    # The authoritative unit price always comes from the server-side
    # article record — the client never supplies a price. The bug is not
    # that the price is spoofable; it's that the *arithmetic* used to
    # scale it by quantity is a legacy fixed-width accumulator.
    line_total_cents = compute_line_total(article["price_cents"], quantity)

    quote_id = secrets.token_hex(16)
    db.execute(
        """INSERT INTO quotes (id, user_id, article_id, quantity, unit_price_cents, line_total_cents)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (quote_id, g.user["id"], article["id"], quantity, article["price_cents"], line_total_cents),
    )
    db.commit()

    return jsonify(
        {
            "quote_id": quote_id,
            "article": article["title"],
            "quantity": quantity,
            "unit_price_cents": article["price_cents"],
            "total_due_cents": line_total_cents,
        }
    )


@bp.route("/confirm", methods=["POST"])
def confirm():
    if g.user is None:
        return jsonify({"error": "You must be logged in to confirm an order."}), 401

    data = request.get_json(silent=True) or {}
    quote_id = data.get("quote_id")
    if not quote_id:
        return jsonify({"error": "quote_id is required."}), 400

    db = get_db()
    q = db.execute(
        "SELECT * FROM quotes WHERE id = ? AND user_id = ? AND consumed = 0",
        (quote_id, g.user["id"]),
    ).fetchone()
    if q is None:
        return jsonify({"error": "Quote not found, already used, or expired."}), 404

    user = db.execute("SELECT * FROM users WHERE id = ?", (g.user["id"],)).fetchone()

    # --- The broken check -------------------------------------------------
    # Billing only verifies that the wallet balance is sufficient to cover
    # the *computed* total. It never independently recomputes the total
    # with correct (non-wrapping) arithmetic, and never questions how a
    # total this small (or negative) could possibly correspond to the
    # quantity being purchased.
    total_due = q["line_total_cents"]
    if user["wallet_cents"] < total_due:
        db.execute("UPDATE quotes SET consumed = 1 WHERE id = ?", (quote_id,))
        db.commit()
        return jsonify({"error": "Insufficient wallet balance.", "wallet_cents": user["wallet_cents"]}), 402

    new_balance = user["wallet_cents"] - total_due
    db.execute("UPDATE users SET wallet_cents = ? WHERE id = ?", (new_balance, user["id"]))

    cur = db.execute(
        """INSERT INTO orders (user_id, article_id, quantity, amount_charged_cents, status)
           VALUES (?, ?, ?, ?, 'paid')""",
        (user["id"], q["article_id"], q["quantity"], total_due),
    )
    order_id = cur.lastrowid

    # --- Entitlements module trusts this blindly ---------------------------
    # See app/entitlements/routes.py / grant_entitlement: it only checks
    # orders.status == 'paid'. It never re-derives the "true" price from
    # the article record using correct arithmetic and compares it to what
    # was actually charged.
    from app.entitlements.routes import grant_entitlement

    grant_entitlement(db, user["id"], q["article_id"], order_id)

    db.execute("UPDATE quotes SET consumed = 1 WHERE id = ?", (quote_id,))
    db.commit()

    return jsonify(
        {
            "status": "paid",
            "order_id": order_id,
            "amount_charged_cents": total_due,
            "wallet_cents": new_balance,
        }
    )
