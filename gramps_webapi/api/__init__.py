"""REST API blueprint."""

from typing import Type

from flask import Blueprint

from ..const import API_PREFIX
from .resources.base import Resource
from .resources.bookmark import BookmarkResource, BookmarksResource
from .resources.citation import CitationResource, CitationsResource
from .resources.event import EventResource, EventsResource
from .resources.family import FamiliesResource, FamilyResource
from .resources.filters import FilterResource
from .resources.media import MediaObjectResource, MediaObjectsResource
from .resources.metadata import MetadataResource
from .resources.note import NoteResource, NotesResource
from .resources.person import PeopleResource, PersonResource
from .resources.place import PlaceResource, PlacesResource
from .resources.relation import RelationResource
from .resources.repository import RepositoriesResource, RepositoryResource
from .resources.source import SourceResource, SourcesResource
from .resources.tag import TagResource, TagsResource
from .resources.token import TokenRefreshResource, TokenResource
from .resources.translate import TranslationResource, TranslationsResource
from .resources.xml import export_xml

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
# Token
register_endpt(TokenResource, "/login/", "token")
register_endpt(TokenRefreshResource, "/refresh/", "token_refresh")
# Bookmark
register_endpt(BookmarkResource, "/bookmarks/<string:namespace>", "bookmark")
register_endpt(BookmarksResource, "/bookmarks/", "bookmarks")
# Filter
register_endpt(FilterResource, "/filters/<string:namespace>", "filter")
# Translate
register_endpt(TranslationResource, "/translations/<string:isocode>", "translation")
register_endpt(TranslationsResource, "/translations/", "translations")
# Relation
register_endpt(
    RelationResource, "/relations/<string:handle1>/<string:handle2>", "relations",
)
# Metadata
register_endpt(MetadataResource, "/metadata/<string:datatype>", "metadata")

# XML export
api_blueprint.route("/xml")(export_xml)
