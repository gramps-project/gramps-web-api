#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2022      David Straub
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

from typing import List, Optional, Type

from flask import current_app
from webargs import fields, validate

from ..const import API_PREFIX
from .auth import jwt_required
from .cache import thumbnail_cache_decorator
from .media import get_media_handler
from .resources.base import Resource
from .resources.bookmarks import (
    BookmarkEditResource,
    BookmarkResource,
    BookmarksResource,
)
from .resources.chat import ChatResource
from .resources.citations import CitationResource, CitationsResource
from .resources.config import ConfigResource, ConfigsResource
from .resources.dna import DnaMatchParserResource, PersonDnaMatchesResource
from .resources.events import EventResource, EventSpanResource, EventsResource
from .resources.export_media import MediaArchiveFileResource, MediaArchiveResource
from .resources.exporters import (
    ExporterFileResource,
    ExporterFileResultResource,
    ExporterResource,
    ExportersResource,
)
from .resources.face_detection import MediaFaceDetectionResource
from .resources.facts import FactsResource
from .resources.families import FamiliesResource, FamilyResource
from .resources.file import MediaFileResource
from .resources.filters import FilterResource, FiltersResource, FiltersResources
from .resources.history import (
    TransactionHistoryResource,
    TransactionUndoResource,
    TransactionsHistoryResource,
)
from .resources.holidays import HolidayResource, HolidaysResource
from .resources.import_media import MediaUploadZipResource
from .resources.importers import (
    ImporterFileResource,
    ImporterResource,
    ImportersResource,
)
from .resources.living import LivingDatesResource, LivingResource
from .resources.media import MediaObjectResource, MediaObjectsResource
from .resources.metadata import MetadataResource
from .resources.name_formats import NameFormatsResource
from .resources.name_groups import NameGroupsResource
from .resources.notes import NoteResource, NotesResource
from .resources.objects import CreateObjectsResource, DeleteObjectsResource
from .resources.ocr import MediaOcrResource
from .resources.people import PeopleResource, PersonResource
from .resources.places import PlaceResource, PlacesResource
from .resources.relations import RelationResource, RelationsResource
from .resources.reports import (
    ReportFileResource,
    ReportFileResultResource,
    ReportResource,
    ReportsResource,
)
from .resources.repositories import RepositoriesResource, RepositoryResource
from .resources.search import SearchIndexResource, SearchResource
from .resources.sources import SourceResource, SourcesResource
from .resources.tags import TagResource, TagsResource
from .resources.tasks import TaskResource
from .resources.timeline import (
    FamilyTimelineResource,
    PersonTimelineResource,
    TimelineFamiliesResource,
    TimelinePeopleResource,
)
from .resources.token import (
    TokenCreateOwnerResource,
    TokenRefreshResource,
    TokenResource,
)
from .resources.oidc import (
    OIDCBackchannelLogoutResource,
    OIDCCallbackResource,
    OIDCConfigResource,
    OIDCLoginResource,
    OIDCLogoutResource,
    OIDCTokenExchangeResource,
)
from .resources.transactions import TransactionsResource
from .resources.translations import TranslationResource, TranslationsResource
from .resources.trees import (
    CheckTreeResource,
    DisableTreeResource,
    EnableTreeResource,
    TreeResource,
    TreesResource,
    UpgradeTreeSchemaResource,
)
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
    UserCreateOwnerResource,
    UserRegisterResource,
    UserResetPasswordResource,
    UserResource,
    UsersResource,
    UserTriggerResetPasswordResource,
)
from .resources.ydna import PersonYDnaResource
from .blueprint import api_blueprint
from .util import get_db_handle, get_tree_from_jwt, parser, use_args


def register_endpt(
    resource: Type[Resource], url: str, name: str, tags: Optional[List[str]] = None
):
    """Register an endpoint."""
    # Register all HTTP methods explicitly so Werkzeug always finds the route
    # and returns 405 (not 404) for methods the view doesn't implement.
    # flask-smorest still only documents methods actually defined on the class.
    kwargs = {}
    if tags is not None:
        kwargs["tags"] = tags
    api_blueprint.add_url_rule(
        url,
        endpoint=name,
        view_func=resource,
        methods=["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"],
        **kwargs,
    )


# Objects
register_endpt(CreateObjectsResource, "/objects/", "objects", tags=["Transactions"])
register_endpt(
    DeleteObjectsResource, "/objects/delete/", "delete_objects", tags=["Transactions"]
)
# Transactions
register_endpt(
    TransactionsResource, "/transactions/", "transactions", tags=["Transactions"]
)
register_endpt(
    TransactionsHistoryResource,
    "/transactions/history/",
    "transactions_history",
    tags=["Transactions"],
)
register_endpt(
    TransactionHistoryResource,
    "/transactions/history/<int:transaction_id>",
    "transaction_history",
    tags=["Transactions"],
)
register_endpt(
    TransactionUndoResource,
    "/transactions/history/<int:transaction_id>/undo",
    "transaction_undo",
    tags=["Transactions"],
)
# Token
register_endpt(TokenResource, "/token/", "token", tags=["Token"])
register_endpt(TokenRefreshResource, "/token/refresh/", "token_refresh", tags=["Token"])
register_endpt(
    TokenCreateOwnerResource,
    "/token/create_owner/",
    "token_create_owner",
    tags=["Token"],
)
# OIDC
register_endpt(OIDCLoginResource, "/oidc/login/", "oidcloginresource", tags=["OIDC"])
register_endpt(
    OIDCCallbackResource, "/oidc/callback/", "oidccallbackresource", tags=["OIDC"]
)
register_endpt(
    OIDCCallbackResource,
    "/oidc/callback/<string:provider_id>",
    "oidccallbackresource_provider",
    tags=["OIDC"],
)
register_endpt(OIDCConfigResource, "/oidc/config/", "oidcconfigresource", tags=["OIDC"])
register_endpt(
    OIDCTokenExchangeResource,
    "/oidc/tokens/",
    "oidctokenexchangeresource",
    tags=["OIDC"],
)
register_endpt(OIDCLogoutResource, "/oidc/logout/", "oidclogoutresource", tags=["OIDC"])
register_endpt(
    OIDCBackchannelLogoutResource,
    "/oidc/backchannel-logout/",
    "oidcbackchannellogoutresource",
    tags=["OIDC"],
)
# People
register_endpt(
    PersonTimelineResource,
    "/people/<string:handle>/timeline",
    "person-timeline",
    tags=["Timeline"],
)
register_endpt(PersonResource, "/people/<string:handle>", "person", tags=["People"])
register_endpt(
    PersonDnaMatchesResource,
    "/people/<string:handle>/dna/matches",
    "person-dna-matches",
    tags=["DNA"],
)
register_endpt(
    PersonYDnaResource, "/people/<string:handle>/ydna", "person-ydna", tags=["DNA"]
)
register_endpt(PeopleResource, "/people/", "people", tags=["People"])
# Families
register_endpt(
    FamilyTimelineResource,
    "/families/<string:handle>/timeline",
    "family-timeline",
    tags=["Timeline"],
)
register_endpt(FamilyResource, "/families/<string:handle>", "family", tags=["Families"])
register_endpt(FamiliesResource, "/families/", "families", tags=["Families"])
# Events
register_endpt(
    EventSpanResource,
    "/events/<string:handle1>/span/<string:handle2>",
    "event-span",
    tags=["Events"],
)
register_endpt(EventResource, "/events/<string:handle>", "event", tags=["Events"])
register_endpt(EventsResource, "/events/", "events", tags=["Events"])
# Timelines
register_endpt(
    TimelinePeopleResource, "/timelines/people/", "timeline-people", tags=["Timeline"]
)
register_endpt(
    TimelineFamiliesResource,
    "/timelines/families/",
    "timeline-families",
    tags=["Timeline"],
)
# Places
register_endpt(PlaceResource, "/places/<string:handle>", "place", tags=["Places"])
register_endpt(PlacesResource, "/places/", "places", tags=["Places"])
# Citations
register_endpt(
    CitationResource, "/citations/<string:handle>", "citation", tags=["Citations"]
)
register_endpt(CitationsResource, "/citations/", "citations", tags=["Citations"])
# Sources
register_endpt(SourceResource, "/sources/<string:handle>", "source", tags=["Sources"])
register_endpt(SourcesResource, "/sources/", "sources", tags=["Sources"])
# Repositories
register_endpt(
    RepositoryResource,
    "/repositories/<string:handle>",
    "repository",
    tags=["Repositories"],
)
register_endpt(
    RepositoriesResource, "/repositories/", "repositories", tags=["Repositories"]
)
# Media
register_endpt(
    MediaObjectResource, "/media/<string:handle>", "media_object", tags=["Media"]
)
register_endpt(MediaObjectsResource, "/media/", "media_objects", tags=["Media"])
# Notes
register_endpt(NoteResource, "/notes/<string:handle>", "note", tags=["Notes"])
register_endpt(NotesResource, "/notes/", "notes", tags=["Notes"])
# Tags
register_endpt(TagResource, "/tags/<string:handle>", "tag", tags=["Tags"])
register_endpt(TagsResource, "/tags/", "tags", tags=["Tags"])
# Trees
register_endpt(TreeResource, "/trees/<string:tree_id>", "tree", tags=["Trees"])
register_endpt(TreesResource, "/trees/", "trees", tags=["Trees"])
register_endpt(
    DisableTreeResource,
    "/trees/<string:tree_id>/disable",
    "disable_tree",
    tags=["Trees"],
)
register_endpt(
    EnableTreeResource, "/trees/<string:tree_id>/enable", "enable_tree", tags=["Trees"]
)
register_endpt(
    CheckTreeResource, "/trees/<string:tree_id>/repair", "repair_tree", tags=["Trees"]
)
register_endpt(
    UpgradeTreeSchemaResource,
    "/trees/<string:tree_id>/migrate",
    "migrate_tree",
    tags=["Trees"],
)
# Types
register_endpt(
    CustomTypeResource, "/types/custom/<string:datatype>", "custom-type", tags=["Types"]
)
register_endpt(CustomTypesResource, "/types/custom/", "custom-types", tags=["Types"])
register_endpt(
    DefaultTypeMapResource,
    "/types/default/<string:datatype>/map",
    "default-type-map",
    tags=["Types"],
)
register_endpt(
    DefaultTypeResource,
    "/types/default/<string:datatype>",
    "default-type",
    tags=["Types"],
)
register_endpt(DefaultTypesResource, "/types/default/", "default-types", tags=["Types"])
register_endpt(TypesResource, "/types/", "types", tags=["Types"])
# Name Formats
register_endpt(
    NameFormatsResource, "/name-formats/", "name-formats", tags=["Name Formats"]
)
# Name Groups
register_endpt(
    NameGroupsResource,
    "/name-groups/<string:surname>/<string:group>",
    "set-name-group",
    tags=["Name Groups"],
)
register_endpt(
    NameGroupsResource,
    "/name-groups/<string:surname>",
    "get-name-group",
    tags=["Name Groups"],
)
register_endpt(NameGroupsResource, "/name-groups/", "name-groups", tags=["Name Groups"])
# Bookmarks
register_endpt(
    BookmarkResource, "/bookmarks/<string:namespace>", "bookmark", tags=["Bookmarks"]
)
register_endpt(BookmarksResource, "/bookmarks/", "bookmarks", tags=["Bookmarks"])
register_endpt(
    BookmarkEditResource,
    "/bookmarks/<string:namespace>/<string:handle>",
    "bookmark_edit",
    tags=["Bookmarks"],
)
# Filters
register_endpt(
    FilterResource,
    "/filters/<string:namespace>/<string:name>",
    "filter",
    tags=["Filters"],
)
register_endpt(
    FiltersResource,
    "/filters/<string:namespace>",
    "filters-namespace",
    tags=["Filters"],
)
register_endpt(FiltersResources, "/filters/", "filters", tags=["Filters"])
# Translations
register_endpt(
    TranslationResource,
    "/translations/<string:language>",
    "translation",
    tags=["Translations"],
)
register_endpt(
    TranslationsResource, "/translations/", "translations", tags=["Translations"]
)
# Parsers
register_endpt(
    DnaMatchParserResource, "/parsers/dna-match", "dna-match-parser", tags=["DNA"]
)
# Relations
register_endpt(
    RelationResource,
    "/relations/<string:handle1>/<string:handle2>",
    "relation",
    tags=["Relations"],
)
register_endpt(
    RelationsResource,
    "/relations/<string:handle1>/<string:handle2>/all",
    "relations",
    tags=["Relations"],
)
# Living
register_endpt(
    LivingDatesResource,
    "/living/<string:handle>/dates",
    "living-dates",
    tags=["Living"],
)
register_endpt(LivingResource, "/living/<string:handle>", "living", tags=["Living"])
# Reports
register_endpt(
    ReportFileResource,
    "/reports/<string:report_id>/file",
    "report-file",
    tags=["Reports"],
)
register_endpt(
    ReportResource, "/reports/<string:report_id>", "report", tags=["Reports"]
)
register_endpt(ReportsResource, "/reports/", "reports", tags=["Reports"])
register_endpt(
    ReportFileResultResource,
    "/reports/<string:report_id>/file/processed/<string:filename>",
    "report-file-result",
    tags=["Reports"],
)
# Facts
register_endpt(FactsResource, "/facts/", "facts", tags=["Facts"])
# Exporters
register_endpt(
    ExporterFileResource,
    "/exporters/<string:extension>/file",
    "exporter-file",
    tags=["Exporters"],
)
register_endpt(
    ExporterFileResultResource,
    "/exporters/<string:extension>/file/processed/<string:filename>",
    "exporter-file-result",
    tags=["Exporters"],
)
register_endpt(
    ExporterResource, "/exporters/<string:extension>", "exporter", tags=["Exporters"]
)
register_endpt(ExportersResource, "/exporters/", "exporters", tags=["Exporters"])
# Importers
register_endpt(
    ImporterFileResource,
    "/importers/<string:extension>/file",
    "importer-file",
    tags=["Importers"],
)
register_endpt(
    ImporterResource, "/importers/<string:extension>", "importer", tags=["Importers"]
)
register_endpt(ImportersResource, "/importers/", "importers", tags=["Importers"])
# Holidays
register_endpt(
    HolidayResource,
    "/holidays/<string:country>/<int:year>/<int:month>/<int:day>",
    "holiday",
    tags=["Holidays"],
)
register_endpt(HolidaysResource, "/holidays/", "holidays", tags=["Holidays"])
# Metadata
register_endpt(MetadataResource, "/metadata/", "metadata", tags=["Metadata"])
# User
register_endpt(UsersResource, "/users/", "users", tags=["Users"])
register_endpt(UserResource, "/users/<string:user_name>/", "user", tags=["Users"])
register_endpt(
    UserRegisterResource,
    "/users/<string:user_name>/register/",
    "register",
    tags=["Users"],
)
register_endpt(
    UserCreateOwnerResource,
    "/users/<string:user_name>/create_owner/",
    "user_create_owner",
    tags=["Users"],
)
register_endpt(
    UserConfirmEmailResource, "/users/-/email/confirm/", "confirm_email", tags=["Users"]
)
register_endpt(
    UserChangePasswordResource,
    "/users/<string:user_name>/password/change",
    "change_password",
    tags=["Users"],
)
register_endpt(
    UserResetPasswordResource,
    "/users/-/password/reset/",
    "reset_password",
    tags=["Users"],
)
register_endpt(
    UserTriggerResetPasswordResource,
    "/users/<string:user_name>/password/reset/trigger/",
    "trigger_reset_password",
    tags=["Users"],
)
# Search
register_endpt(SearchResource, "/search/", "search", tags=["Search"])
register_endpt(SearchIndexResource, "/search/index/", "search_index", tags=["Search"])

# Chat
register_endpt(ChatResource, "/chat/", "chat", tags=["Chat"])

# Config
register_endpt(ConfigsResource, "/config/", "configs", tags=["Config"])
register_endpt(ConfigResource, "/config/<string:key>/", "config", tags=["Config"])

# Tasks
register_endpt(TaskResource, "/tasks/<string:task_id>", "task", tags=["Tasks"])

# Media files
register_endpt(
    MediaFileResource, "/media/<string:handle>/file", "media_file", tags=["Media"]
)

# Face detection
register_endpt(
    MediaFaceDetectionResource,
    "/media/<string:handle>/face_detection",
    "media_face_detection",
    tags=["Media"],
)
# OCR
register_endpt(
    MediaOcrResource, "/media/<string:handle>/ocr", "media_ocr", tags=["Media"]
)

# Media export
register_endpt(MediaArchiveResource, "/media/archive/", "media_archive", tags=["Media"])

# Media export
register_endpt(
    MediaArchiveFileResource,
    "/media/archive/<string:filename>",
    "media_archive_filename",
    tags=["Media"],
)

# Media import
register_endpt(
    MediaUploadZipResource,
    "/media/archive/upload/zip",
    "media_archive_upload_zip",
    tags=["Media"],
)


# Thumbnails
@api_blueprint.route("/media/<string:handle>/thumbnail/<int:size>")
@jwt_required
@use_args(
    {
        "square": fields.Boolean(load_default=False),
        "jwt": fields.String(required=False),
    },
    location="query",
)
@thumbnail_cache_decorator
def get_thumbnail(args, handle, size):
    """Get a file's thumbnail."""
    tree = get_tree_from_jwt()
    db_handle = get_db_handle()
    handler = get_media_handler(db_handle, tree=tree).get_file_handler(
        handle, db_handle=db_handle
    )
    return handler.send_thumbnail(size=size, square=args["square"])


@api_blueprint.route(
    "/media/<string:handle>/cropped/<int:x1>/<int:y1>/<int:x2>/<int:y2>"
)
@jwt_required
@use_args(
    {
        "square": fields.Boolean(load_default=False),
        "jwt": fields.String(required=False),
    },
    location="query",
)
@thumbnail_cache_decorator
def get_cropped(args, handle: str, x1: int, y1: int, x2: int, y2: int):
    """Get the thumbnail of a cropped file."""
    tree = get_tree_from_jwt()
    db_handle = get_db_handle()
    handler = get_media_handler(db_handle, tree=tree).get_file_handler(
        handle, db_handle=db_handle
    )
    return handler.send_cropped(x1=x1, y1=y1, x2=x2, y2=y2, square=args["square"])


@api_blueprint.route(
    "/media/<string:handle>/cropped/<int:x1>/<int:y1>/<int:x2>/<int:y2>/thumbnail/<int:size>"
)
@jwt_required
@use_args(
    {
        "square": fields.Boolean(load_default=False),
        "jwt": fields.String(required=False),
    },
    location="query",
)
@thumbnail_cache_decorator
def get_thumbnail_cropped(
    args, handle: str, x1: int, y1: int, x2: int, y2: int, size: int
):
    """Get the thumbnail of a cropped file."""
    tree = get_tree_from_jwt()
    db_handle = get_db_handle()
    handler = get_media_handler(db_handle, tree=tree).get_file_handler(
        handle, db_handle=db_handle
    )
    return handler.send_thumbnail_cropped(
        size=size, x1=x1, y1=y1, x2=x2, y2=y2, square=args["square"]
    )
