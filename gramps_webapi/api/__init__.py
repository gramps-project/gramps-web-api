"""REST API blueprint."""

from typing import Type

from flask import Blueprint

from ..const import API_PREFIX
from .resources.base import Resource
from .resources.person import PeopleResource, PersonResource
from .resources.family import FamiliesResource, FamilyResource
from .resources.source import SourcesResource, SourceResource
from .resources.citation import CitationsResource, CitationResource
from .resources.event import EventsResource, EventResource
from .resources.media import MediaObjectsResource, MediaObjectResource
from .resources.place import PlacesResource, PlaceResource
from .resources.repository import RepositoriesResource, RepositoryResource
from .resources.note import NotesResource, NoteResource
from .resources.tag import TagsResource, TagResource
from .resources.token import TokenRefreshResource, TokenResource


api_blueprint = Blueprint("api", __name__, url_prefix=API_PREFIX)


def register_endpt(resource: Type[Resource], url: str, name: str):
    """Register an endpoint."""
    api_blueprint.add_url_rule(url, view_func=resource.as_view(name))


# Person
register_endpt(PersonResource, "/person/<string:handle>", "person")
register_endpt(PeopleResource, "/person/", "people")
# Family
register_endpt(FamilyResource, "/family/<string:handle>", "family")
register_endpt(FamiliesResource, "/family/", "families")
# Source
register_endpt(SourceResource, "/source/<string:handle>", "source")
register_endpt(SourcesResource, "/source/", "sources")
# Citation
register_endpt(CitationResource, "/citation/<string:handle>", "citation")
register_endpt(CitationsResource, "/citation/", "citations")
# Event
register_endpt(EventResource, "/event/<string:handle>", "event")
register_endpt(EventsResource, "/event/", "events")
# Media Object
register_endpt(MediaObjectResource, "/media/<string:handle>", "media_object")
register_endpt(MediaObjectsResource, "/media/", "media_objects")
# Place
register_endpt(PlaceResource, "/place/<string:handle>", "place")
register_endpt(PlacesResource, "/place/", "places")
# Repository
register_endpt(RepositoryResource, "/repository/<string:handle>", "repository")
register_endpt(RepositoriesResource, "/repository/", "repositories")
# Note
register_endpt(NoteResource, "/note/<string:handle>", "note")
register_endpt(NotesResource, "/note/", "notes")
# Tag
register_endpt(TagResource, "/tag/<string:handle>", "tag")
register_endpt(TagsResource, "/tag/", "tags")
# Token
register_endpt(TokenResource, "/login/", "token")
register_endpt(TokenRefreshResource, "/refresh/", "token_refresh")
