"""REST API blueprint."""

from flask import Blueprint
from flask_restful import Api

from ..const import API_PREFIX
from .resources.person import PeopleResource, PersonResource
from .resources.token import TokenResource

api_blueprint = Blueprint("api", __name__, url_prefix=API_PREFIX)
api = Api(api_blueprint)


api.add_resource(PersonResource, "/person/<string:gramps_id>")
api.add_resource(PeopleResource, "/people/")
api.add_resource(TokenResource, "/login/")
