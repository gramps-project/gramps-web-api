#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
# Copyright (C) 2023-24   David Straub
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

"""Metadata API resource."""

from importlib import metadata

import gramps_ql as gql
import object_ql as oql
import pytesseract
import sifts
from flask import Response, current_app
from gramps.gen.const import ENV, GRAMPS_LOCALE
from gramps.gen.db.base import DbReadBase
from gramps.gen.db.generic import DbGeneric
from gramps.gen.db.utils import get_dbid_from_path
from gramps.gen.utils.grampslocale import INCOMPLETE_TRANSLATIONS
from webargs import fields

from gramps_webapi.const import TREE_MULTI, VERSION

from ...auth.const import PERM_VIEW_PRIVATE
from ...dbmanager import WebDbManager
from ..auth import has_permissions
from ..search import get_search_indexer, get_semantic_search_indexer
from ..util import get_db_handle, get_tree_from_jwt_or_fail, use_args
from . import ProtectedResource
from .emit import GrampsJSONEncoder


def get_dbid_from_tree_id(tree_id: str) -> str:
    """Get the database ID (e.g. 'sqlite') from a tree ID."""
    dbmgr = WebDbManager(
        dirname=tree_id,
        create_if_missing=False,
        ignore_lock=current_app.config["IGNORE_DB_LOCK"],
    )
    db_path = dbmgr.path
    return get_dbid_from_path(db_path)


class MetadataResource(ProtectedResource, GrampsJSONEncoder):
    """Metadata resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_db_handle()

    @use_args(
        {
            "surnames": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def get(self, args) -> Response:
        """Get active database and application related metadata information."""
        catalog = GRAMPS_LOCALE.get_language_dict()
        for entry in catalog:
            if catalog[entry] == GRAMPS_LOCALE.language[0]:
                language_name = entry
                break

        db_handle = self.db_handle
        db_name = db_handle.get_dbname()
        tree_id = get_tree_from_jwt_or_fail()
        db_type = get_dbid_from_tree_id(tree_id)
        is_multi_tree = current_app.config["TREE"] == TREE_MULTI
        has_task_queue = bool(current_app.config["CELERY_CONFIG"])
        has_semantic_search = bool(current_app.config["VECTOR_EMBEDDING_MODEL"])
        has_chat = has_semantic_search and bool(current_app.config["LLM_MODEL"])

        try:
            pytesseract.get_tesseract_version()
            has_ocr = True
            ocr_languages = [
                lang for lang in pytesseract.get_languages() if lang != "osd"
            ]
        except pytesseract.TesseractNotFoundError:
            has_ocr = False
            ocr_languages = []
        searcher = get_search_indexer(tree_id)
        search_count = searcher.count(
            include_private=has_permissions({PERM_VIEW_PRIVATE})
        )
        sifts_info = {
            "version": sifts.__version__,
            "count": search_count,
        }
        if current_app.config.get("VECTOR_EMBEDDING_MODEL"):
            searcher_s = get_semantic_search_indexer(tree_id)
            search_count_s = searcher_s.count(
                include_private=has_permissions({PERM_VIEW_PRIVATE})
            )
            sifts_info["count_semantic"] = search_count_s

        result = {
            "database": {
                "id": db_handle.get_dbid(),
                "name": db_name,
                "type": db_type,
            },
            "default_person": db_handle.get_default_handle(),
            "gramps": {
                "version": ENV["VERSION"],
            },
            "gramps_webapi": {
                "schema": VERSION,
                "version": VERSION,
            },
            "gramps_ql": {"version": gql.__version__},
            "object_ql": {"version": oql.__version__},
            "yclade": {"version": metadata.version("yclade")},
            "locale": {
                "lang": GRAMPS_LOCALE.lang,
                "language": GRAMPS_LOCALE.language[0],
                "description": language_name,
                "incomplete_translation": bool(
                    GRAMPS_LOCALE.language[0] in INCOMPLETE_TRANSLATIONS
                ),
            },
            "object_counts": {
                "people": db_handle.get_number_of_people(),
                "families": db_handle.get_number_of_families(),
                "sources": db_handle.get_number_of_sources(),
                "citations": db_handle.get_number_of_citations(),
                "events": db_handle.get_number_of_events(),
                "media": db_handle.get_number_of_media(),
                "places": db_handle.get_number_of_places(),
                "repositories": db_handle.get_number_of_repositories(),
                "notes": db_handle.get_number_of_notes(),
                "tags": db_handle.get_number_of_tags(),
            },
            "researcher": db_handle.get_researcher(),
            "search": {
                "sifts": sifts_info,
            },
            "server": {
                "multi_tree": is_multi_tree,
                "task_queue": has_task_queue,
                "ocr": has_ocr,
                "ocr_languages": ocr_languages,
                "semantic_search": has_semantic_search,
                "chat": has_chat,
            },
        }
        if args["surnames"]:
            result["surnames"] = db_handle.get_surname_list()
        data = db_handle.get_summary()
        db_version_key = GRAMPS_LOCALE.translation.sgettext("Database version")
        db_module_key = GRAMPS_LOCALE.translation.sgettext("Database module version")
        db_schema_key = GRAMPS_LOCALE.translation.sgettext("Schema version")
        for item in data:
            if item == db_version_key:
                result["database"]["version"] = data[item]
            elif item == db_module_key:
                result["database"]["module"] = data[item]
            elif item == db_schema_key:
                result["database"]["schema"] = data[item]
        if isinstance(db_handle, DbGeneric):
            result["database"]["actual_schema"] = db_handle.get_schema_version()
        return self.response(200, result)
