#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""REST API blueprint."""

from typing import Type

from flask import Blueprint, current_app
from webargs import fields, validate
from webargs.flaskparser import use_args

from ..const import API_PREFIX
from .auth import jwt_required_ifauth
from .file import LocalFileHandler
from .resources.base import Resource
from .resources.bookmarks import BookmarkResource, BookmarksResource
from .resources.citations import CitationResource, CitationsResource
from .resources.events import EventResource, EventsResource
from .resources.exporters import (
    ExporterFileResource,
    ExporterResource,
    ExportersResource,
)
from .resources.families import FamiliesResource, FamilyResource
from .resources.filters import FilterResource, FiltersResource, FiltersResources
from .resources.media import MediaObjectResource, MediaObjectsResource
from .resources.metadata import MetadataResource
from .resources.name_formats import NameFormatsResource
from .resources.name_groups import NameGroupsResource
from .resources.notes import NoteResource, NotesResource
from .resources.people import PeopleResource, PersonResource
from .resources.places import PlaceResource, PlacesResource
from .resources.relations import RelationResource, RelationsResource
from .resources.reports import ReportResource, ReportRunnerResource, ReportsResource
from .resources.repositories import RepositoriesResource, RepositoryResource
from .resources.sources import SourceResource, SourcesResource
from .resources.tags import TagResource, TagsResource
from .resources.token import TokenRefreshResource, TokenResource
from .resources.translations import TranslationResource, TranslationsResource
from .resources.types import (
    CustomTypeResource,
    CustomTypesResource,
    DefaultTypeMapResource,
    DefaultTypeResource,
    DefaultTypesResource,
    TypesResource,
)
from .resources.user import UserChangePasswordResource

api_blueprint = Blueprint("api", __name__, url_prefix=API_PREFIX)


def register_endpt(resource: Type[Resource], url: str, name: str):
    """Register an endpoint."""
    api_blueprint.add_url_rule(url, view_func=resource.as_view(name))


# Token
register_endpt(TokenResource, "/login/", "token")
register_endpt(TokenRefreshResource, "/refresh/", "token_refresh")
# People
register_endpt(PersonResource, "/people/<string:handle>", "person")
register_endpt(PeopleResource, "/people/", "people")
# Families
register_endpt(FamilyResource, "/families/<string:handle>", "family")
register_endpt(FamiliesResource, "/families/", "families")
# Events
register_endpt(EventResource, "/events/<string:handle>", "event")
register_endpt(EventsResource, "/events/", "events")
# Places
register_endpt(PlaceResource, "/places/<string:handle>", "place")
register_endpt(PlacesResource, "/places/", "places")
# Citations
register_endpt(CitationResource, "/citations/<string:handle>", "citation")
register_endpt(CitationsResource, "/citations/", "citations")
# Sources
register_endpt(SourceResource, "/sources/<string:handle>", "source")
register_endpt(SourcesResource, "/sources/", "sources")
# Repositories
register_endpt(RepositoryResource, "/repositories/<string:handle>", "repository")
register_endpt(RepositoriesResource, "/repositories/", "repositories")
# Media
register_endpt(MediaObjectResource, "/media/<string:handle>", "media_object")
register_endpt(MediaObjectsResource, "/media/", "media_objects")
# Notes
register_endpt(NoteResource, "/notes/<string:handle>", "note")
register_endpt(NotesResource, "/notes/", "notes")
# Tags
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
register_endpt(TypesResource, "/types/", "types")
# Name Formats
register_endpt(NameFormatsResource, "/name-formats/", "name-formats")
# Name Groups
register_endpt(
    NameGroupsResource, "/name-groups/<string:surname>/<string:group>", "set-name-group"
)
register_endpt(NameGroupsResource, "/name-groups/<string:surname>", "get-name-group")
register_endpt(NameGroupsResource, "/name-groups/", "name-groups")
# Bookmarks
register_endpt(BookmarkResource, "/bookmarks/<string:namespace>", "bookmark")
register_endpt(BookmarksResource, "/bookmarks/", "bookmarks")
# Filters
register_endpt(FilterResource, "/filters/<string:namespace>/<string:name>", "filter")
register_endpt(FiltersResource, "/filters/<string:namespace>", "filters-namespace")
register_endpt(FiltersResources, "/filters/", "filters")
# Translations
register_endpt(TranslationResource, "/translations/<string:language>", "translation")
register_endpt(TranslationsResource, "/translations/", "translations")
# Relations
register_endpt(
    RelationResource,
    "/relations/<string:handle1>/<string:handle2>",
    "relation",
)
register_endpt(
    RelationsResource,
    "/relations/<string:handle1>/<string:handle2>/all",
    "relations",
)
# Reports
register_endpt(ReportRunnerResource, "/reports/<string:id>/file", "run-report")
register_endpt(ReportResource, "/reports/<string:id>", "report")
register_endpt(ReportsResource, "/reports/", "reports")
# Exporters
register_endpt(
    ExporterFileResource, "/exporters/<string:extension>/file", "exporter-file"
)
register_endpt(ExporterResource, "/exporters/<string:extension>", "exporter")
register_endpt(ExportersResource, "/exporters/", "exporters")
# Metadata
register_endpt(MetadataResource, "/metadata/", "metadata")
# User
register_endpt(UserChangePasswordResource, "/user/password/change", "change_password")

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
