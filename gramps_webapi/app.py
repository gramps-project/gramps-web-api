"""Flask web app providing a REST API to a gramps family tree."""

import logging
import os

from flask import Flask, current_app, g

from .dbmanager import DbState, WebDbManager
from .api import api_blueprint


def get_db() -> DbState:
    """Open the database and get the current state.

    Called before every request.
    """
    dbmgr = current_app.config["DB_MANAGER"]
    if "dbstate" not in g:
        g.dbstate = dbmgr.get_db()
    return g.dbstate


def create_app():
    """Flask application factory."""
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = True
    app.logger.setLevel(logging.INFO)
    app.config["TREE"] = os.getenv("TREE")
    if not app.config["TREE"]:
        raise ValueError("You have to set the `TREE` environment variable.")
    app.config["DB_MANAGER"] = WebDbManager(name=app.config["TREE"])

    app.register_blueprint(api_blueprint)

    # close DB after every request
    @app.teardown_appcontext
    def close_db(exception) -> None:
        """Close the database."""
        dbstate = g.pop("dbstate", None)
        if dbstate and dbstate.is_open():
            dbstate.db.close()

    @app.route("/", methods=["GET", "POST"])
    def dummy_root():
        dbstate = get_db()
        dbname = dbstate.db.get_dbname()
        res = dbstate.db.get_researcher().get_name()
        return "Database: {}, Researcher: {}".format(dbname, res)

    return app
