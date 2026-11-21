import os
import secrets

from flask import Flask

from app.db import init_db, register_db_teardown
from app.challenge.final_flag import init_flag


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", secrets.token_hex(32)),
        DATABASE_PATH=os.environ.get("DATABASE_PATH", "/tmp/linas_blog.sqlite3"),
    )

    if test_config:
        app.config.update(test_config)

    register_db_teardown(app)

    with app.app_context():
        init_db(app)
        init_flag(app)

    from app.auth.routes import bp as auth_bp
    from app.articles.routes import bp as articles_bp
    from app.checkout.routes import bp as checkout_bp
    from app.entitlements.routes import bp as entitlements_bp
    from app.challenge.routes import bp as challenge_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(articles_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(entitlements_bp)
    app.register_blueprint(challenge_bp)

    return app
