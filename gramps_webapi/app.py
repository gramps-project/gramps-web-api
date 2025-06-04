#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2022      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Flask web app providing a REST API to a Gramps family tree."""

import logging
import os
import warnings
from typing import Any, Dict, Optional
from auth.oidc import configure_oauth, oidc_bp
from dotenv import load_dotenv

from flask import Flask, abort, g, send_from_directory, session
from flask_compress import Compress
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from gramps.gen.config import config as gramps_config
from gramps.gen.config import set as setconfig

from .api import api_blueprint
from .api.cache import thumbnail_cache
from .api.ratelimiter import limiter
from .api.search.embeddings import load_model
from .api.util import close_db
from .auth import user_db
from .config import DefaultConfig, DefaultConfigJWT
from .const import API_PREFIX, ENV_CONFIG_FILE, TREE_MULTI
from .dbmanager import WebDbManager
from .util.celery import create_celery

load_dotenv()

def deprecated_config_from_env(app):
    """Add deprecated config from environment variables.

    This function will be removed eventually!
    """
    options = [
        "TREE",
        "SECRET_KEY",
        "USER_DB_URI",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "MEDIA_BASE_DIR",
        "SEARCH_INDEX_DIR",
        "EMAIL_HOST",
        "EMAIL_PORT",
        "EMAIL_HOST_USER",
        "EMAIL_HOST_PASSWORD",
        "DEFAULT_FROM_EMAIL",
        "BASE_URL",
        "STATIC_PATH",
    ]
    for option in options:
        value = os.getenv(option)
        if value:
            app.config[option] = value
            warnings.warn(
                f"Setting the `{option}` config option via the `{option}` environment"
                " variable is deprecated and will stop working in the future."
                f" Please use `GRAMPSWEB_{option}` instead."
            )
    return app


def create_app(config: Optional[Dict[str, Any]] = None):
    """Flask application factory."""
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY")
    app.logger.setLevel(logging.INFO)

    # load default config
    app.config.from_object(DefaultConfig)

    # overwrite with user config file
    if os.getenv(ENV_CONFIG_FILE):
        app.config.from_envvar(ENV_CONFIG_FILE)

    # use unprefixed environment variables if exist - deprecated!
    deprecated_config_from_env(app)

    # use prefixed environment variables if exist
    app.config.from_prefixed_env(prefix="GRAMPSWEB")

    # update config from dictionary if present
    if config:
        app.config.update(**config)

    # fail if required config option is missing
    required_options = ["TREE", "SECRET_KEY", "USER_DB_URI"]
    for option in required_options:
        if not app.config.get(option):
            raise ValueError(f"{option} must be specified")

    # environment variable to set the Gramps database path.
    # Needed for backwards compatibility from Gramps 6.0 onwards
    if db_path := os.getenv("GRAMPS_DATABASE_PATH"):
        setconfig("database.path", db_path)

    if app.config.get("LOG_LEVEL"):
        app.logger.setLevel(app.config["LOG_LEVEL"])

    if app.config["TREE"] != TREE_MULTI:
        # create database if missing (only in single-tree mode)
        WebDbManager(
            name=app.config["TREE"],
            create_if_missing=True,
            ignore_lock=app.config["IGNORE_DB_LOCK"],
        )

    if app.config["TREE"] == TREE_MULTI and not app.config["MEDIA_PREFIX_TREE"]:
        warnings.warn(
            "You have enabled multi-tree support, but `MEDIA_PREFIX_TREE` is "
            "set to `False`. This is strongly discouraged as it exposes media "
            "files to users belonging to different trees!"
        )

    if app.config["TREE"] == TREE_MULTI and app.config["NEW_DB_BACKEND"] != "sqlite":
        # needed in case a new postgres tree is to be created
        gramps_config.set("database.host", app.config["POSTGRES_HOST"])
        gramps_config.set("database.port", str(app.config["POSTGRES_PORT"]))

    # load JWT default settings
    app.config.from_object(DefaultConfigJWT)

    # instantiate JWT manager
    JWTManager(app)

    app.config["SQLALCHEMY_DATABASE_URI"] = app.config["USER_DB_URI"]
    user_db.init_app(app)

    configure_oauth(app)
    app.register_blueprint(oidc_bp)
    
    thumbnail_cache.init_app(app, config=app.config["THUMBNAIL_CACHE_CONFIG"])

    # enable CORS for /api/... resources
    if app.config.get("CORS_ORIGINS"):
        CORS(
            app,
            resources={f"{API_PREFIX}/*": {"origins": app.config["CORS_ORIGINS"]}},
        )

    # enable gzip compression
    Compress(app)

    static_path = app.config.get("STATIC_PATH")

    # routes for static hosting (e.g. SPA frontend)
    @app.route("/", methods=["GET", "POST"])
    def send_index():
        return send_from_directory(static_path, "index.html")

    @app.route("/<path:path>", methods=["GET", "POST"])
    def send_static(path):
        if path.startswith(API_PREFIX[1:]):
            # we don't want any erroneous API calls to end up here!
            abort(404)
        if path and os.path.exists(os.path.join(static_path, path)):
            return send_from_directory(static_path, path)
        else:
            return send_from_directory(static_path, "index.html")

    # register the API blueprint
    app.register_blueprint(api_blueprint)
    limiter.init_app(app)

    # instantiate celery
    create_celery(app)

    @app.teardown_appcontext
    def close_db_connection(exception) -> None:
        """Close the Gramps database after every request."""
        db = g.pop("db", None)
        if db:
            close_db(db)
        db_write = g.pop("db_write", None)
        if db_write:
            close_db(db_write)

    @app.teardown_request
    def close_user_db_connection(exception) -> None:
        """Close the user database after every request."""
        if exception:
            user_db.session.rollback()  # pylint: disable=no-member
        user_db.session.close()  # pylint: disable=no-member
        user_db.session.remove()  # pylint: disable=no-member

    if app.config.get("VECTOR_EMBEDDING_MODEL"):
        app.config["_INITIALIZED_VECTOR_EMBEDDING_MODEL"] = load_model(
            app.config["VECTOR_EMBEDDING_MODEL"]
        )

    @app.route("/ready", methods=["GET"])
    def ready():
        return {"status": "ready"}, 200

    @oidc_bp.route("/callback/<provider>")
    def authorize(provider):
        client = oauth.create_client(provider)
        token = client.authorize_access_token()
        oidc_user = client.parse_id_token(token) if provider == "google" else client.get('user').json()
        
        # Get email from OIDC user info
        email = oidc_user.get('email')
        if not email:
            return {"error": "No email provided by OIDC provider"}, 400
        
        # Check if user exists
        query = user_db.session.query(User)
        user = query.filter_by(email=email).scalar()
        
        if not user:
            # Create new user with default role
            try:
                user = User(
                    id=uuid.uuid4(),
                    name=email.split('@')[0],  # Use part before @ as username
                    email=email,
                    fullname=oidc_user.get('name', ''),
                    role=0,  # Default role
                    pwhash='',  # No password for OIDC users
                )
                user_db.session.add(user)
                user_db.session.commit()
            except IntegrityError:
                return {"error": "User creation failed"}, 400
        
        # Set up session
        session['user_id'] = str(user.id)
        session['user_name'] = user.name
        session['user_role'] = user.role
        
        return {"status": "logged_in", "provider": provider, "user": {
            "name": user.name,
            "email": user.email,
            "full_name": user.fullname,
            "role": user.role
        }}

    return app