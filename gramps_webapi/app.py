"""Flask web app providing a REST API to a gramps family tree."""

import logging

from flask import Flask, g
from flask_compress import Compress
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from .api import api_blueprint
from .api.resources.token import limiter
from .auth import SQLAuth
from .config import DefaultConfig, DefaultConfigJWT
from .const import API_PREFIX, ENV_CONFIG_FILE
from .dbmanager import WebDbManager


def create_app(db_manager=None):
    """Flask application factory."""
    app = Flask(__name__)
    app.logger.setLevel(logging.INFO)

    # load default config
    app.config.from_object(DefaultConfig)

    # overwrite with user config file
    app.config.from_envvar(ENV_CONFIG_FILE)

    # instantiate DB manager
    if db_manager is None:
        app.config["DB_MANAGER"] = WebDbManager(name=app.config["TREE"])
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
        if not app.config.get("USER_DB_URI"):
            raise ValueError("USER_DB_URI must be specified")
        app.config["AUTH_PROVIDER"] = SQLAuth(db_uri=app.config["USER_DB_URI"])

    # enable CORS for /api/... resources
    if app.config.get("CORS_ORIGINS"):
        CORS(
            app,
            resources={
                "{}/*".format(API_PREFIX): {"origins": app.config["CORS_ORIGINS"]}
            },
        )

    # enable gzip compression
    Compress(app)

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

    return app
