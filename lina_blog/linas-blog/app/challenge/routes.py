from flask import Blueprint, render_template, abort, g

from app.db import get_db
from app.challenge.final_flag import get_flag

bp = Blueprint("challenge", __name__, url_prefix="/premium")


def _has_entitlement(db, user_id, article_id):
    return (
        db.execute(
            "SELECT 1 FROM entitlements WHERE user_id = ? AND article_id = ?",
            (user_id, article_id),
        ).fetchone()
        is not None
    )


@bp.route("/<slug>")
def premium_article(slug):
    if g.user is None:
        abort(401)

    db = get_db()
    article = db.execute(
        "SELECT * FROM articles WHERE slug = ? AND access = 'premium'", (slug,)
    ).fetchone()
    if article is None:
        abort(404)

    if not _has_entitlement(db, g.user["id"], article["id"]):
        abort(403)

    body = article["body"]
    flag = None
    if slug == "lina-private-research":
        # The single final flag is only ever rendered here, and only once
        # a genuine entitlement row exists for this exact article.
        flag = get_flag()

    return render_template("premium_article.html", article=article, flag=flag)
