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

from flask import Flask, abort, g, send_from_directory
from flask_compress import Compress
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from .api import api_blueprint
from .api.cache import thumbnail_cache
from .api.ratelimiter import limiter
from .api.search import SearchIndexer
from .auth import SQLAuth
from .config import DefaultConfig, DefaultConfigJWT
from .const import API_PREFIX, ENV_CONFIG_FILE
from .dbmanager import WebDbManager
from .util.celery import create_celery


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

    app.logger.setLevel(logging.INFO)

    # when using gunicorn, make sure flask log messages are shown
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

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

    # create database if missing
    WebDbManager(name=app.config["TREE"], create_if_missing=True)

    # load JWT default settings
    app.config.from_object(DefaultConfigJWT)

    # instantiate JWT manager
    JWTManager(app)

    app.config["AUTH_PROVIDER"] = SQLAuth(db_uri=app.config["USER_DB_URI"])

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

    # close DB after every request
    @app.teardown_appcontext
    def close_db(exception) -> None:
        """Close the database."""
        db = g.pop("db", None)
        if db and db.is_open():
            db.close()
        db_write = g.pop("db_write", None)
        if db_write and db_write.is_open():
            db_write.close()

    return app
