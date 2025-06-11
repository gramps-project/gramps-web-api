"""Flask web app providing a REST API to a Gramps family tree."""


import logging
import os
import warnings
from typing import Any, Dict, Optional


from flask import Flask, abort, g, send_from_directory
from flask_compress import Compress
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from gramps.gen.config import config as gramps_config
from gramps.gen.config import set as setconfig


from .api import api_blueprint
from .api.cache import thumbnail_cache, request_cache
from .api.ratelimiter import limiter
from .api.search.embeddings import load_model
from .api.util import close_db
from .auth import user_db
from .auth.oidc import configure_oauth, oidc_bp
from .config import DefaultConfig, DefaultConfigJWT
from .const import API_PREFIX, ENV_CONFIG_FILE, TREE_MULTI
from .dbmanager import WebDbManager
from .util.celery import create_celery


def deprecated_config_from_env(app):
    """Add deprecated config from environment variables (legacy support)."""
    options = [
        "TREE", "SECRET_KEY", "USER_DB_URI", "POSTGRES_USER", "POSTGRES_PASSWORD",
        "MEDIA_BASE_DIR", "SEARCH_INDEX_DIR", "EMAIL_HOST", "EMAIL_PORT",
        "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD", "DEFAULT_FROM_EMAIL",
        "BASE_URL", "STATIC_PATH",
    ]
    for option in options:
        value = os.getenv(option)
        if value:
            app.config[option] = value
            warnings.warn(
                f"Setting `{option}` via the environment is deprecated. "
                f"Use `GRAMPSWEB_{option}` instead."
            )
    return app


def create_app(config: Optional[Dict[str, Any]] = None, config_from_env: bool = True):
    """Flask application factory."""
    app = Flask(__name__)
    app.logger.setLevel(logging.INFO)


    app.config.from_object(DefaultConfig)


    if os.getenv(ENV_CONFIG_FILE):
        app.config.from_envvar(ENV_CONFIG_FILE)


    deprecated_config_from_env(app)


    if config_from_env:
        app.config.from_prefixed_env(prefix="GRAMPSWEB")


    if config:
        app.config.update(**config)


    required_options = ["TREE", "SECRET_KEY", "USER_DB_URI"]
    for option in required_options:
        if not app.config.get(option):
            raise ValueError(f"{option} must be specified")


    if db_path := os.getenv("GRAMPS_DATABASE_PATH"):
        setconfig("database.path", db_path)


    if app.config.get("LOG_LEVEL"):
        app.logger.setLevel(app.config["LOG_LEVEL"])


    if app.config["TREE"] != TREE_MULTI:
        WebDbManager(
            name=app.config["TREE"],
            create_if_missing=True,
            ignore_lock=app.config["IGNORE_DB_LOCK"],
        )


    if app.config["TREE"] == TREE_MULTI and not app.config["MEDIA_PREFIX_TREE"]:
        warnings.warn("Multi-tree mode is enabled but MEDIA_PREFIX_TREE is False.")


    if app.config["TREE"] == TREE_MULTI and app.config["NEW_DB_BACKEND"] != "sqlite":
        gramps_config.set("database.host", app.config["POSTGRES_HOST"])
        gramps_config.set("database.port", str(app.config["POSTGRES_PORT"]))


    app.config.from_object(DefaultConfigJWT)
    JWTManager(app)


    app.config["SQLALCHEMY_DATABASE_URI"] = app.config["USER_DB_URI"]
    user_db.init_app(app)


    request_cache.init_app(app, config=app.config["REQUEST_CACHE_CONFIG"])


    configure_oauth(app)
    app.register_blueprint(oidc_bp)


    thumbnail_cache.init_app(app, config=app.config["THUMBNAIL_CACHE_CONFIG"])


    if app.config.get("CORS_ORIGINS"):
        CORS(app, resources={f"{API_PREFIX}/*": {"origins": app.config["CORS_ORIGINS"]}})


    Compress(app)


    static_path = app.config.get("STATIC_PATH")


    @app.route("/", methods=["GET", "POST"])
    def send_index():
        return send_from_directory(static_path, "index.html")


    @app.route("/<path:path>", methods=["GET", "POST"])
    def send_static(path):
        if path.startswith(API_PREFIX[1:]):
            abort(404)
        if path and os.path.exists(os.path.join(static_path, path)):
            return send_from_directory(static_path, path)
        return send_from_directory(static_path, "index.html")


    app.register_blueprint(api_blueprint)
    limiter.init_app(app)
    create_celery(app)


    @app.teardown_appcontext
    def close_db_connection(exception) -> None:
        db = g.pop("db", None)
        if db:
            close_db(db)
        db_write = g.pop("db_write", None)
        if db_write:
            close_db(db_write)


    @app.teardown_request
    def close_user_db_connection(exception) -> None:
        if exception:
            user_db.session.rollback()
        user_db.session.close()
        user_db.session.remove()


    if app.config.get("VECTOR_EMBEDDING_MODEL"):
        app.config["_INITIALIZED_VECTOR_EMBEDDING_MODEL"] = load_model(
            app.config["VECTOR_EMBEDDING_MODEL"]
        )


    @app.route("/ready", methods=["GET"])
    def ready():
        return {"status": "ready"}, 200


    return app
