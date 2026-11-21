from flask import Blueprint, render_template, abort, g, session

from app.db import get_db

bp = Blueprint("articles", __name__)


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        db = get_db()
        g.user = db.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


@bp.route("/")
def index():
    db = get_db()
    articles = db.execute(
        "SELECT * FROM articles ORDER BY id ASC"
    ).fetchall()
    return render_template("index.html", articles=articles)


@bp.route("/pricing")
def pricing():
    db = get_db()
    articles = db.execute(
        "SELECT * FROM articles WHERE access = 'premium' ORDER BY price_cents ASC"
    ).fetchall()
    return render_template("pricing.html", articles=articles)


@bp.route("/articles/<slug>")
def article_detail(slug):
    db = get_db()
    article = db.execute(
        "SELECT * FROM articles WHERE slug = ?", (slug,)
    ).fetchone()
    if article is None:
        abort(404)

    if article["access"] == "free":
        return render_template("article_free.html", article=article)

    # Premium article: only ever show a teaser here. The real body is
    # served exclusively from the /premium/<slug> endpoint after an
    # entitlement check.
    owned = False
    if g.user is not None:
        owned = (
            db.execute(
                "SELECT 1 FROM entitlements WHERE user_id = ? AND article_id = ?",
                (g.user["id"], article["id"]),
            ).fetchone()
            is not None
        )
    return render_template("article_preview.html", article=article, owned=owned)
