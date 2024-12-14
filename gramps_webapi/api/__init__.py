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

from typing import Type

from flask import Blueprint, current_app
from webargs import fields, validate

from ..const import API_PREFIX
from .auth import jwt_required
from .cache import thumbnail_cache
from .media import get_media_handler
from .resources.base import Resource

from .util import get_db_handle, get_tree_from_jwt, make_cache_key_thumbnails, use_args

api_blueprint = Blueprint("api", __name__, url_prefix=API_PREFIX)


def register_endpt(resource: Type[Resource], url: str, name: str):
    """Register an endpoint."""
    api_blueprint.add_url_rule(url, view_func=resource.as_view(name))


# Objects
def register_objects():
    from .resources.objects import CreateObjectsResource, DeleteObjectsResource
    register_endpt(CreateObjectsResource, "/objects/", "objects")
    register_endpt(DeleteObjectsResource, "/objects/delete/", "delete_objects")

# Transactions
def register_transations():
    from .resources.history import TransactionHistoryResource, TransactionsHistoryResource
    from .resources.transactions import TransactionsResource
    register_endpt(TransactionsResource, "/transactions/", "transactions")
    register_endpt(
        TransactionsHistoryResource, "/transactions/history/", "transactions_history"
    )
    register_endpt(
        TransactionHistoryResource,
        "/transactions/history/<int:transaction_id>",
        "transaction_history",
    )

# Token
def register_token():
    from .resources.token import (
        TokenCreateOwnerResource,
        TokenRefreshResource,
        TokenResource,
    )
    register_endpt(TokenResource, "/token/", "token")
    register_endpt(TokenRefreshResource, "/token/refresh/", "token_refresh")
    register_endpt(TokenCreateOwnerResource, "/token/create_owner/", "token_create_owner")

# People
def register_people():
    from .resources.people import PeopleResource, PersonResource
    from .resources.dna import PersonDnaMatchesResource
    from .resources.timeline import (
        PersonTimelineResource,
    )
    register_endpt(
        PersonTimelineResource, "/people/<string:handle>/timeline", "person-timeline"
    )
    register_endpt(PersonResource, "/people/<string:handle>", "person")
    register_endpt(
        PersonDnaMatchesResource,
        "/people/<string:handle>/dna/matches",
        "person-dna-matches",
    )
    register_endpt(PeopleResource, "/people/", "people")

# Families
def register_family():
    from .resources.families import FamiliesResource, FamilyResource
    from .resources.timeline import (
        FamilyTimelineResource,
    )
    register_endpt(
        FamilyTimelineResource, "/families/<string:handle>/timeline", "family-timeline"
    )
    register_endpt(FamilyResource, "/families/<string:handle>", "family")
    register_endpt(FamiliesResource, "/families/", "families")

# Events
def register_event():
    from .resources.events import EventResource, EventSpanResource, EventsResource
    register_endpt(
        EventSpanResource, "/events/<string:handle1>/span/<string:handle2>", "event-span"
    )
    register_endpt(EventResource, "/events/<string:handle>", "event")
    register_endpt(EventsResource, "/events/", "events")

# Timelines
def register_timelines():
    from .resources.timeline import (
        TimelineFamiliesResource,
        TimelinePeopleResource,
    )
    register_endpt(TimelinePeopleResource, "/timelines/people/", "timeline-people")
    register_endpt(TimelineFamiliesResource, "/timelines/families/", "timeline-families")

# Places
def register_places():
    from .resources.places import PlaceResource, PlacesResource
    register_endpt(PlaceResource, "/places/<string:handle>", "place")
    register_endpt(PlacesResource, "/places/", "places")

# Citations
def register_citations():
    from .resources.citations import CitationResource, CitationsResource
    register_endpt(CitationResource, "/citations/<string:handle>", "citation")
    register_endpt(CitationsResource, "/citations/", "citations")

# Sources
def register_sources():
    from .resources.sources import SourceResource, SourcesResource
    register_endpt(SourceResource, "/sources/<string:handle>", "source")
    register_endpt(SourcesResource, "/sources/", "sources")

# Repositories
def register_repositories():
    from .resources.repositories import RepositoriesResource, RepositoryResource
    register_endpt(RepositoryResource, "/repositories/<string:handle>", "repository")
    register_endpt(RepositoriesResource, "/repositories/", "repositories")

# Media
def register_media():
    from .resources.media import MediaObjectResource, MediaObjectsResource
    register_endpt(MediaObjectResource, "/media/<string:handle>", "media_object")
    register_endpt(MediaObjectsResource, "/media/", "media_objects")

# Notes
def register_notes():
    from .resources.notes import NoteResource, NotesResource
    register_endpt(NoteResource, "/notes/<string:handle>", "note")
    register_endpt(NotesResource, "/notes/", "notes")

# Tags
def register_tags():
    from .resources.tags import TagResource, TagsResource
    register_endpt(TagResource, "/tags/<string:handle>", "tag")
    register_endpt(TagsResource, "/tags/", "tags")

# Trees
def register_trees():
    from .resources.trees import (
        CheckTreeResource,
        DisableTreeResource,
        EnableTreeResource,
        TreeResource,
        TreesResource,
        UpgradeTreeSchemaResource,
    )
    register_endpt(TreeResource, "/trees/<string:tree_id>", "tree")
    register_endpt(TreesResource, "/trees/", "trees")
    register_endpt(DisableTreeResource, "/trees/<string:tree_id>/disable", "disable_tree")
    register_endpt(EnableTreeResource, "/trees/<string:tree_id>/enable", "enable_tree")
    register_endpt(CheckTreeResource, "/trees/<string:tree_id>/repair", "repair_tree")
    register_endpt(
        UpgradeTreeSchemaResource, "/trees/<string:tree_id>/migrate", "migrate_tree"
    )

# Types
def register_types():
    from .resources.types import (
        CustomTypeResource,
        CustomTypesResource,
        DefaultTypeMapResource,
        DefaultTypeResource,
        DefaultTypesResource,
        TypesResource,
    )
    register_endpt(CustomTypeResource, "/types/custom/<string:datatype>", "custom-type")
    register_endpt(CustomTypesResource, "/types/custom/", "custom-types")
    register_endpt(
        DefaultTypeMapResource, "/types/default/<string:datatype>/map", "default-type-map"
    )
    register_endpt(DefaultTypeResource, "/types/default/<string:datatype>", "default-type")
    register_endpt(DefaultTypesResource, "/types/default/", "default-types")
    register_endpt(TypesResource, "/types/", "types")

# Name Formats
def register_name_formats():
    from .resources.name_formats import NameFormatsResource
    register_endpt(NameFormatsResource, "/name-formats/", "name-formats")

# Name Groups
def register_name_groups():
    from .resources.name_groups import NameGroupsResource
    register_endpt(
        NameGroupsResource, "/name-groups/<string:surname>/<string:group>", "set-name-group"
    )
    register_endpt(NameGroupsResource, "/name-groups/<string:surname>", "get-name-group")
    register_endpt(NameGroupsResource, "/name-groups/", "name-groups")

# Bookmarks
def register_bookmarks():
    from .resources.bookmarks import (
        BookmarkEditResource,
        BookmarkResource,
        BookmarksResource,
    )
    register_endpt(BookmarkResource, "/bookmarks/<string:namespace>", "bookmark")
    register_endpt(BookmarksResource, "/bookmarks/", "bookmarks")
    register_endpt(
        BookmarkEditResource,
        "/bookmarks/<string:namespace>/<string:handle>",
        "bookmark_edit",
    )

# Filters
def register_filters():
    from .resources.filters import FilterResource, FiltersResource, FiltersResources
    register_endpt(FilterResource, "/filters/<string:namespace>/<string:name>", "filter")
    register_endpt(FiltersResource, "/filters/<string:namespace>", "filters-namespace")
    register_endpt(FiltersResources, "/filters/", "filters")

# Translations
def register_translations():
    from .resources.translations import TranslationResource, TranslationsResource
    register_endpt(TranslationResource, "/translations/<string:language>", "translation")
    register_endpt(TranslationsResource, "/translations/", "translations")

# Relations
def register_relations():
    from .resources.relations import RelationResource, RelationsResource
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
def register_living():
    from .resources.living import LivingDatesResource, LivingResource
    register_endpt(LivingDatesResource, "/living/<string:handle>/dates", "living-dates")
    register_endpt(LivingResource, "/living/<string:handle>", "living")

# Reports
def register_reports():
    from .resources.reports import (
        ReportFileResource,
        ReportFileResultResource,
        ReportResource,
        ReportsResource,
    )
    register_endpt(ReportFileResource, "/reports/<string:report_id>/file", "report-file")
    register_endpt(ReportResource, "/reports/<string:report_id>", "report")
    register_endpt(ReportsResource, "/reports/", "reports")
    register_endpt(
        ReportFileResultResource,
        "/reports/<string:report_id>/file/processed/<string:filename>",
        "report-file-result",
    )

# Facts
def register_facts():
    from .resources.facts import FactsResource
    register_endpt(FactsResource, "/facts/", "facts")

# Exporters
def register_exporters():
    from .resources.exporters import (
        ExporterFileResource,
        ExporterFileResultResource,
        ExporterResource,
        ExportersResource,
    )
    register_endpt(
        ExporterFileResource, "/exporters/<string:extension>/file", "exporter-file"
    )
    register_endpt(
        ExporterFileResultResource,
        "/exporters/<string:extension>/file/processed/<string:filename>",
        "exporter-file-result",
    )
    register_endpt(ExporterResource, "/exporters/<string:extension>", "exporter")
    register_endpt(ExportersResource, "/exporters/", "exporters")

# Importers
def register_importers():
    from .resources.importers import (
        ImporterFileResource,
        ImporterResource,
        ImportersResource,
    )
    register_endpt(
        ImporterFileResource, "/importers/<string:extension>/file", "importer-file"
    )
    register_endpt(ImporterResource, "/importers/<string:extension>", "importer")
    register_endpt(ImportersResource, "/importers/", "importers")

# Holidays
def register_holidays():
    from .resources.holidays import HolidayResource, HolidaysResource
    register_endpt(
        HolidayResource,
        "/holidays/<string:country>/<int:year>/<int:month>/<int:day>",
        "holiday",
    )
    register_endpt(HolidaysResource, "/holidays/", "holidays")

# Metadata
def register_metadata():
    from .resources.metadata import MetadataResource
    register_endpt(MetadataResource, "/metadata/", "metadata")

# User
def register_user():
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
        UserCreateOwnerResource,
        "/users/<string:user_name>/create_owner/",
        "user_create_owner",
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
def register_search():
    from .resources.search import SearchIndexResource, SearchResource
    register_endpt(SearchResource, "/search/", "search")
    register_endpt(SearchIndexResource, "/search/index/", "search_index")

# Chat
def register_chat():
    from .resources.chat import ChatResource
    register_endpt(ChatResource, "/chat/", "chat")

# Config
def register_config():
    from .resources.config import ConfigResource, ConfigsResource

    register_endpt(
        ConfigsResource,
        "/config/",
        "configs",
    )
    register_endpt(
        ConfigResource,
        "/config/<string:key>/",
        "config",
    )

# Tasks
def register_tasks():
    from .resources.tasks import TaskResource
    register_endpt(
        TaskResource,
        "/tasks/<string:task_id>",
        "task",
    )

# Media files
def register_media_files():
    from .resources.file import MediaFileResource
    register_endpt(
        MediaFileResource,
        "/media/<string:handle>/file",
        "media_file",
    )

# Face detection
def register_face_detection():
    from .resources.face_detection import MediaFaceDetectionResource
    register_endpt(
        MediaFaceDetectionResource,
        "/media/<string:handle>/face_detection",
        "media_face_detection",
    )

# OCR
def register_ocr():
    from .resources.ocr import MediaOcrResource
    register_endpt(
        MediaOcrResource,
        "/media/<string:handle>/ocr",
        "media_ocr",
    )

# Media export
def register_media_export():
    from .resources.export_media import MediaArchiveFileResource, MediaArchiveResource
    register_endpt(
        MediaArchiveResource,
        "/media/archive/",
        "media_archive",
    )

    register_endpt(
        MediaArchiveFileResource,
        "/media/archive/<string:filename>",
        "media_archive_filename",
    )

# Media import
def register_media_import():
    from .resources.import_media import MediaUploadZipResource
    register_endpt(
        MediaUploadZipResource,
        "/media/archive/upload/zip",
        "media_archive_upload_zip",
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
@thumbnail_cache.cached(make_cache_key=make_cache_key_thumbnails)
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
@thumbnail_cache.cached(make_cache_key=make_cache_key_thumbnails)
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
@thumbnail_cache.cached(make_cache_key=make_cache_key_thumbnails)
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

ENDPOINT_MAP = {
    "bookmarks": register_bookmarks,
    "chat": register_chat,
    "citations": register_citations,
    "config": register_config,
    "event": register_event,
    "exporters": register_exporters,
    "face_detection": register_face_detection,
    "facts": register_facts,
    "family": register_family,
    "filters": register_filters,
    "holidays": register_holidays,
    "importers": register_importers,
    "living": register_living,
    "media": register_media,
    "media_export": register_media_export,
    "media_files": register_media_files,
    "media_import": register_media_import,
    "metadata": register_metadata,
    "name_formats": register_name_formats,
    "name_groups": register_name_groups,
    "notes": register_notes,
    "objects": register_objects,
    "ocr": register_ocr,
    "people": register_people,
    "places": register_places,
    "relations": register_relations,
    "reports": register_reports,
    "repositories": register_repositories,
    "search": register_search,
    "sources": register_sources,
    "tags": register_tags,
    "tasks": register_tasks,
    "timelines": register_timelines,
    "token": register_token,
    "transations": register_transations,
    "translations": register_translations,
    "trees": register_trees,
    "types": register_types,
    "user": register_user,
}

def register_endpoints(endpoints):
    """
    Given a list of endpoint group names, register
    all of the endpoints in that group.
    """
    for group_name in endpoints:
        if group_name in ENDPOINT_MAP:
            ENDPOINT_MAP[group_name]()
        else:
            raise Exception("Unknown endpoint group name: %r" % group_name)

# For now, register them all
register_endpoints(ENDPOINT_MAP.keys())
