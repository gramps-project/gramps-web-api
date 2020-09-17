"""Flask web app providing a REST API to a gramps family tree."""

import logging
import os

from flask import Flask, current_app, g
from flask_compress import Compress
from flask_cors import CORS

from .api import api_blueprint
from .const import API_PREFIX, ENV_CONFIG_FILE
from .dbmanager import WebDbManager


def create_app():
    """Flask application factory."""
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = True
    app.logger.setLevel(logging.INFO)
    app.config.from_envvar(ENV_CONFIG_FILE)
    app.config["DB_MANAGER"] = WebDbManager(name=app.config["TREE"])

    if app.config.get("CORS_ORIGINS"):
        CORS(
            app,
            resources={
                "{}/*".format(API_PREFIX): {"origins": app.config["CORS_ORIGINS"]}
            },
        )

    Compress(app)

    app.register_blueprint(api_blueprint)

    # close DB after every request
    @app.teardown_appcontext
    def close_db(exception) -> None:
        """Close the database."""
        dbstate = g.pop("dbstate", None)
        if dbstate and dbstate.is_open():
            dbstate.db.close()

    return app
