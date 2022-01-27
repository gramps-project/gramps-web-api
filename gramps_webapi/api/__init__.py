#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""REST API blueprint."""

from typing import Type

from flask import Blueprint, current_app
from flask_caching import Cache
from webargs import fields, validate

from ..const import API_PREFIX
from .auth import jwt_required_ifauth
from .media import MediaHandler
from .resources.base import Resource
from .resources.bookmarks import BookmarkResource, BookmarksResource
from .resources.citations import CitationResource, CitationsResource
from .resources.events import EventResource, EventSpanResource, EventsResource
from .resources.exporters import (
    ExporterFileResource,
    ExporterResource,
    ExportersResource,
)
from .resources.facts import FactsResource
from .resources.families import FamiliesResource, FamilyResource
from .resources.file import MediaFileResource
from .resources.filters import FilterResource, FiltersResource, FiltersResources
from .resources.holidays import HolidayResource, HolidaysResource
from .resources.living import LivingDatesResource, LivingResource
from .resources.media import MediaObjectResource, MediaObjectsResource
from .resources.metadata import MetadataResource
from .resources.name_formats import NameFormatsResource
from .resources.name_groups import NameGroupsResource
from .resources.notes import NoteResource, NotesResource
from .resources.people import PeopleResource, PersonResource
from .resources.places import PlaceResource, PlacesResource
from .resources.relations import RelationResource, RelationsResource
from .resources.reports import ReportFileResource, ReportResource, ReportsResource
from .resources.repositories import RepositoriesResource, RepositoryResource
from .resources.search import SearchResource
from .resources.sources import SourceResource, SourcesResource
from .resources.tags import TagResource, TagsResource
from .resources.timeline import (
    FamilyTimelineResource,
    PersonTimelineResource,
    TimelineFamiliesResource,
    TimelinePeopleResource,
)
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
from .resources.user import (
    UserChangePasswordResource,
    UserConfirmEmailResource,
    UserRegisterResource,
    UserResetPasswordResource,
    UserResource,
    UsersResource,
    UserTriggerResetPasswordResource,
)
from .resources.objects import CreateObjectsResource
from .resources.transactions import TransactionsResource
from .util import make_cache_key_thumbnails, use_args

api_blueprint = Blueprint("api", __name__, url_prefix=API_PREFIX)
thumbnail_cache = Cache()


def register_endpt(resource: Type[Resource], url: str, name: str):
    """Register an endpoint."""
    api_blueprint.add_url_rule(url, view_func=resource.as_view(name))


# Objects
register_endpt(CreateObjectsResource, "/objects/", "objects")
# Transactions
register_endpt(TransactionsResource, "/transactions/", "transactions")
# Token
register_endpt(TokenResource, "/token/", "token")
register_endpt(TokenRefreshResource, "/token/refresh/", "token_refresh")
# People
register_endpt(
    PersonTimelineResource, "/people/<string:handle>/timeline", "person-timeline"
)
register_endpt(PersonResource, "/people/<string:handle>", "person")
register_endpt(PeopleResource, "/people/", "people")
# Families
register_endpt(
    FamilyTimelineResource, "/families/<string:handle>/timeline", "family-timeline"
)
register_endpt(FamilyResource, "/families/<string:handle>", "family")
register_endpt(FamiliesResource, "/families/", "families")
# Events
register_endpt(
    EventSpanResource, "/events/<string:handle1>/span/<string:handle2>", "event-span"
)
register_endpt(EventResource, "/events/<string:handle>", "event")
register_endpt(EventsResource, "/events/", "events")
# Timelines
register_endpt(TimelinePeopleResource, "/timelines/people/", "timeline-people")
register_endpt(TimelineFamiliesResource, "/timelines/families/", "timeline-families")
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
# Living
register_endpt(LivingDatesResource, "/living/<string:handle>/dates", "living-dates")
register_endpt(LivingResource, "/living/<string:handle>", "living")
# Reports
register_endpt(ReportFileResource, "/reports/<string:report_id>/file", "report-file")
register_endpt(ReportResource, "/reports/<string:report_id>", "report")
register_endpt(ReportsResource, "/reports/", "reports")
# Facts
register_endpt(FactsResource, "/facts/", "facts")
# Exporters
register_endpt(
    ExporterFileResource, "/exporters/<string:extension>/file", "exporter-file"
)
register_endpt(ExporterResource, "/exporters/<string:extension>", "exporter")
register_endpt(ExportersResource, "/exporters/", "exporters")
# Holidays
register_endpt(
    HolidayResource,
    "/holidays/<string:country>/<int:year>/<int:month>/<int:day>",
    "holiday",
)
register_endpt(HolidaysResource, "/holidays/", "holidays")
# Metadata
register_endpt(MetadataResource, "/metadata/", "metadata")
# User
register_endpt(
    UsersResource,
    "/users/",
    "users",
)
register_endpt(
    UserResource,
    "/users/<string:user_name>/",
    "user",
)
register_endpt(
    UserRegisterResource,
    "/users/<string:user_name>/register/",
    "register",
)
register_endpt(
    UserConfirmEmailResource,
    "/users/-/email/confirm/",
    "confirm_email",
)
register_endpt(
    UserChangePasswordResource,
    "/users/<string:user_name>/password/change",
    "change_password",
)
register_endpt(
    UserResetPasswordResource,
    "/users/-/password/reset/",
    "reset_password",
)
register_endpt(
    UserTriggerResetPasswordResource,
    "/users/<string:user_name>/password/reset/trigger/",
    "trigger_reset_password",
)
# Search
register_endpt(SearchResource, "/search/", "search")

register_endpt(
    MediaFileResource,
    "/media/<string:handle>/file",
    "media_file",
)


# Thumbnails
@api_blueprint.route("/media/<string:handle>/thumbnail/<int:size>")
@jwt_required_ifauth
@use_args(
    {"square": fields.Boolean(missing=False), "jwt": fields.String(required=False)},
    location="query",
)
@thumbnail_cache.cached(make_cache_key=make_cache_key_thumbnails)
def get_thumbnail(args, handle, size):
    """Get a file's thumbnail."""
    base_dir = current_app.config.get("MEDIA_BASE_DIR", "")
    handler = MediaHandler(base_dir).get_file_handler(handle)
    return handler.send_thumbnail(size=size, square=args["square"])


@api_blueprint.route(
    "/media/<string:handle>/cropped/<int:x1>/<int:y1>/<int:x2>/<int:y2>"
)
@jwt_required_ifauth
@use_args(
    {"square": fields.Boolean(missing=False), "jwt": fields.String(required=False)},
    location="query",
)
@thumbnail_cache.cached(make_cache_key=make_cache_key_thumbnails)
def get_cropped(args, handle: str, x1: int, y1: int, x2: int, y2: int):
    """Get the thumbnail of a cropped file."""
    base_dir = current_app.config.get("MEDIA_BASE_DIR", "")
    handler = MediaHandler(base_dir).get_file_handler(handle)
    return handler.send_cropped(x1=x1, y1=y1, x2=x2, y2=y2, square=args["square"])


@api_blueprint.route(
    "/media/<string:handle>/cropped/<int:x1>/<int:y1>/<int:x2>/<int:y2>/thumbnail/<int:size>"
)
@jwt_required_ifauth
@use_args(
    {"square": fields.Boolean(missing=False), "jwt": fields.String(required=False)},
    location="query",
)
@thumbnail_cache.cached(make_cache_key=make_cache_key_thumbnails)
def get_thumbnail_cropped(
    args, handle: str, x1: int, y1: int, x2: int, y2: int, size: int
):
    """Get the thumbnail of a cropped file."""
    base_dir = current_app.config.get("MEDIA_BASE_DIR", "")
    handler = MediaHandler(base_dir).get_file_handler(handle)
    return handler.send_thumbnail_cropped(
        size=size, x1=x1, y1=y1, x2=x2, y2=y2, square=args["square"]
    )
