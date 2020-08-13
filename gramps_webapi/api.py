"""Flask web app providing a REST API to a gramps family tree."""

import logging

from flask import Flask
from flask_restful import Api, Resource


def create_app():
    """Flask application factory."""
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = True
    app.logger.setLevel(logging.INFO)

    # REST API
    api = Api(app)

    @app.route("/", methods=["GET", "POST"])
    def dummy_root():
        return "Hello Gramps."

    class DummyEndpoint(Resource):
        """A dummy endpoint."""

        def get(self):
            return {"key": "value"}

    api.add_resource(DummyEndpoint, "/api/dummy")
    return app
