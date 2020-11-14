"""REST API blueprint."""

from typing import Type

from flask import Blueprint, current_app
from webargs import fields, validate
from webargs.flaskparser import use_args

from ..const import API_PREFIX
from .auth import jwt_required_ifauth
from .file import LocalFileHandler
from .resources.base import Resource
from .resources.bookmark import BookmarkResource, BookmarksResource
from .resources.citation import CitationResource, CitationsResource
from .resources.event import EventResource, EventsResource
from .resources.family import FamiliesResource, FamilyResource
from .resources.filters import FilterResource, FiltersResource
from .resources.media import MediaObjectResource, MediaObjectsResource
from .resources.metadata import MetadataResource
from .resources.name_groups import NameGroupsResource
from .resources.note import NoteResource, NotesResource
from .resources.person import PeopleResource, PersonResource
from .resources.place import PlaceResource, PlacesResource
from .resources.relation import RelationResource
from .resources.repository import RepositoriesResource, RepositoryResource
from .resources.source import SourceResource, SourcesResource
from .resources.tag import TagResource, TagsResource
from .resources.token import TokenRefreshResource, TokenResource
from .resources.translate import TranslationResource, TranslationsResource
from .resources.types import (
    CustomTypeResource,
    CustomTypesResource,
    DefaultTypeMapResource,
    DefaultTypeResource,
    DefaultTypesResource,
    TypesResource,
)

api_blueprint = Blueprint("api", __name__, url_prefix=API_PREFIX)


def register_endpt(resource: Type[Resource], url: str, name: str):
    """Register an endpoint."""
    api_blueprint.add_url_rule(url, view_func=resource.as_view(name))


# Person
register_endpt(PersonResource, "/people/<string:handle>", "person")
register_endpt(PeopleResource, "/people/", "people")
# Family
register_endpt(FamilyResource, "/families/<string:handle>", "family")
register_endpt(FamiliesResource, "/families/", "families")
# Source
register_endpt(SourceResource, "/sources/<string:handle>", "source")
register_endpt(SourcesResource, "/sources/", "sources")
# Citation
register_endpt(CitationResource, "/citations/<string:handle>", "citation")
register_endpt(CitationsResource, "/citations/", "citations")
# Event
register_endpt(EventResource, "/events/<string:handle>", "event")
register_endpt(EventsResource, "/events/", "events")
# Media Object
register_endpt(MediaObjectResource, "/media/<string:handle>", "media_object")
register_endpt(MediaObjectsResource, "/media/", "media_objects")
# Place
register_endpt(PlaceResource, "/places/<string:handle>", "place")
register_endpt(PlacesResource, "/places/", "places")
# Repository
register_endpt(RepositoryResource, "/repositories/<string:handle>", "repository")
register_endpt(RepositoriesResource, "/repositories/", "repositories")
# Note
register_endpt(NoteResource, "/notes/<string:handle>", "note")
register_endpt(NotesResource, "/notes/", "notes")
# Tag
register_endpt(TagResource, "/tags/<string:handle>", "tag")
register_endpt(TagsResource, "/tags/", "tags")
# Types
register_endpt(CustomTypeResource, "/types/custom/<string:datatype>", "custom-type")
register_endpt(CustomTypesResource, "/types/custom/", "custom-types")
register_endpt(
    DefaultTypeMapResource, "/types/default/<string:datatype>/map", "default-type-map"
)
register_endpt(DefaultTypeResource, "/types/default/<string:datatype>", "default-type")
register_endpt(DefaultTypesResource, "/types/default/", "default-types")
register_endpt(TypesResource, "/types/", "all-types")
# Token
register_endpt(TokenResource, "/login/", "token")
register_endpt(TokenRefreshResource, "/refresh/", "token_refresh")
# Name Groups
register_endpt(
    NameGroupsResource, "/name-groups/<string:surname>/<string:group>", "set-name-group"
)
register_endpt(NameGroupsResource, "/name-groups/<string:surname>", "get-name-group")
register_endpt(NameGroupsResource, "/name-groups/", "name-groups")
# Bookmark
register_endpt(BookmarkResource, "/bookmarks/<string:namespace>", "bookmark")
register_endpt(BookmarksResource, "/bookmarks/", "bookmarks")
# Filter
register_endpt(FilterResource, "/filters/<string:namespace>/<string:name>", "filter")
register_endpt(FiltersResource, "/filters/<string:namespace>", "filters")
# Translate
register_endpt(TranslationResource, "/translations/<string:isocode>", "translation")
register_endpt(TranslationsResource, "/translations/", "translations")
# Relation
register_endpt(
    RelationResource,
    "/relations/<string:handle1>/<string:handle2>",
    "relations",
)
# Metadata
register_endpt(MetadataResource, "/metadata/<string:datatype>", "metadata")

# Media files
@api_blueprint.route("/media/<string:handle>/file")
@jwt_required_ifauth
def download_file(handle):
    """Download a file."""
    base_dir = current_app.config.get("MEDIA_BASE_DIR")
    handler = LocalFileHandler(handle, base_dir)
    return handler.send_file()


# Media files
@api_blueprint.route("/media/<string:handle>/thumbnail/<int:size>")
@jwt_required_ifauth
@use_args({"square": fields.Boolean(missing=False)}, location="query")
def get_thumbnail(args, handle, size):
    """Get a file's thumbnail."""
    base_dir = current_app.config.get("MEDIA_BASE_DIR")
    handler = LocalFileHandler(handle, base_dir)
    return handler.send_thumbnail(size=size, square=args["square"])


@api_blueprint.route(
    "/media/<string:handle>/cropped/<int:x1>/<int:y1>/<int:x2>/<int:y2>"
)
@jwt_required_ifauth
@use_args({"square": fields.Boolean(missing=False)}, location="query")
def get_cropped(args, handle: str, x1: int, y1: int, x2: int, y2: int):
    """Get the thumbnail of a cropped file."""
    base_dir = current_app.config.get("MEDIA_BASE_DIR")
    handler = LocalFileHandler(handle, base_dir)
    return handler.send_cropped(x1=x1, y1=y1, x2=x2, y2=y2, square=args["square"])


@api_blueprint.route(
    "/media/<string:handle>/cropped/<int:x1>/<int:y1>/<int:x2>/<int:y2>/thumbnail/<int:size>"
)
@jwt_required_ifauth
@use_args({"square": fields.Boolean(missing=False)}, location="query")
def get_thumbnail_cropped(
    args, handle: str, x1: int, y1: int, x2: int, y2: int, size: int
):
    """Get the thumbnail of a cropped file."""
    base_dir = current_app.config.get("MEDIA_BASE_DIR")
    handler = LocalFileHandler(handle, base_dir)
    return handler.send_thumbnail_cropped(
        size=size, x1=x1, y1=y1, x2=x2, y2=y2, square=args["square"]
    )
