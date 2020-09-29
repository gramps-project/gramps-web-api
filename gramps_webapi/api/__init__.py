"""REST API blueprint."""

from flask import Blueprint
from flask_restful import Api

from ..const import API_PREFIX
from .resources.person import PeopleResource, PersonResource
from .resources.family import FamiliesResource, FamilyResource
from .resources.token import TokenRefreshResource, TokenResource

api_blueprint = Blueprint("api", __name__, url_prefix=API_PREFIX)
api = Api(api_blueprint)


api.add_resource(PersonResource, "/person/<string:gramps_id>")
api.add_resource(PeopleResource, "/person/")
api.add_resource(FamilyResource, "/family/<string:gramps_id>")
api.add_resource(FamiliesResource, "/family/")
api.add_resource(TokenResource, "/login/")
api.add_resource(TokenRefreshResource, "/refresh/")
