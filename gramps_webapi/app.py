#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Flask web app providing a REST API to a gramps family tree."""

import logging
import os

from flask import Flask, abort, g, send_from_directory
from flask_compress import Compress
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from .api import api_blueprint, thumbnail_cache
from .api.resources.token import limiter
from .api.search import SearchIndexer
from .auth import SQLAuth
from .config import DefaultConfig, DefaultConfigJWT
from .const import API_PREFIX, ENV_CONFIG_FILE
from .dbmanager import WebDbManager


def create_app(db_manager=None):
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

    # if tree is missing, try to get it from the env or fail
    app.config["TREE"] = app.config.get("TREE") or os.getenv("TREE")
    if not app.config.get("TREE"):
        raise ValueError("TREE must be specified")

    # if secret key is missing, try to get it from the env
    app.config["SECRET_KEY"] = app.config["SECRET_KEY"] or os.getenv("SECRET_KEY")
    # still not found? Fail, unless auth is disabled
    if not app.config.get("SECRET_KEY") and not app.config.get("DISABLE_AUTH"):
        raise ValueError("SECRET_KEY must be specified")

    # if postgresql user/password is missing, try to get  it from the env
    app.config["POSTGRES_USER"] = app.config["POSTGRES_USER"] or os.getenv(
        "POSTGRES_USER"
    )
    app.config["POSTGRES_PASSWORD"] = app.config["POSTGRES_PASSWORD"] or os.getenv(
        "POSTGRES_PASSWORD"
    )

    # try setting media basedir from environment
    app.config["MEDIA_BASE_DIR"] = app.config.get("MEDIA_BASE_DIR") or os.getenv(
        "MEDIA_BASE_DIR"
    )

    # instantiate DB manager
    if db_manager is None:
        app.config["DB_MANAGER"] = WebDbManager(
            name=app.config["TREE"],
            username=app.config["POSTGRES_USER"],
            password=app.config["POSTGRES_PASSWORD"],
        )
    else:
        app.config["DB_MANAGER"] = db_manager

    if app.config.get("DISABLE_AUTH"):
        pass
    else:
        # load JWT default settings
        app.config.from_object(DefaultConfigJWT)

        # instantiate JWT manager
        JWTManager(app)

        # instantiate and store auth provider
        # if DB URI is missing, try to get it from the env or fail
        app.config["USER_DB_URI"] = app.config.get("USER_DB_URI") or os.getenv(
            "USER_DB_URI"
        )
        if not app.config.get("USER_DB_URI"):
            raise ValueError("USER_DB_URI must be specified")
        app.config["AUTH_PROVIDER"] = SQLAuth(db_uri=app.config["USER_DB_URI"])

    thumbnail_cache.init_app(app, config=app.config["THUMBNAIL_CACHE_CONFIG"])

    # search indexer
    app.config["SEARCH_INDEXER"] = SearchIndexer(app.config["SEARCH_INDEX_DIR"])

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

    # close DB after every request
    @app.teardown_appcontext
    def close_db(exception) -> None:
        """Close the database."""
        dbstate = g.pop("dbstate", None)
        if dbstate and dbstate.is_open():
            dbstate.db.close()
        dbstate_write = g.pop("dbstate_write", None)
        if dbstate_write and dbstate_write.is_open():
            dbstate_write.db.close()

    return app
