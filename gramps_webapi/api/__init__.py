"""REST API blueprint."""

from typing import Type

from flask import Blueprint

from ..const import API_PREFIX
from .resources.base import Resource
from .resources.person import PeopleResource, PersonResource
from .resources.token import TokenRefreshResource, TokenResource


api_blueprint = Blueprint("api", __name__, url_prefix=API_PREFIX)


def register_endpt(resource: Type[Resource], url: str, name: str):
    """Register an endpoint."""
    api_blueprint.add_url_rule(url, view_func=resource.as_view(name))


# Person
register_endpt(PersonResource, "/person/<string:gramps_id>", "person")
register_endpt(PeopleResource, "/person/", "people")
# Token
register_endpt(TokenResource, "/login/", "token")
register_endpt(TokenRefreshResource, "/refresh/", "token_refresh")
