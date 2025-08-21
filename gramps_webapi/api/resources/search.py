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

"""Full-text search endpoint."""

from __future__ import annotations

import re
from typing import Dict, Optional

from flask import Response
from flask_jwt_extended import get_jwt_identity
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from gramps.gen.utils.grampslocale import GrampsLocale
from webargs import fields, validate

from ...auth.const import PERM_TRIGGER_REINDEX, PERM_VIEW_PRIVATE
from ...const import PRIMARY_GRAMPS_OBJECTS
from ..auth import has_permissions, require_permissions
from ..search import (
    SearchIndexer,
    SemanticSearchIndexer,
    get_search_indexer,
    get_semantic_search_indexer,
)
from ..tasks import (
    AsyncResult,
    make_task_response,
    run_task,
    search_reindex_full,
    search_reindex_incremental,
)
from ..util import (
    get_db_handle,
    get_locale_for_language,
    get_tree_from_jwt_or_fail,
    use_args,
)
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .util import (
    abort_with_message,
    get_citation_profile_for_object,
    get_event_profile_for_object,
    get_family_profile_for_object,
    get_media_profile_for_object,
    get_person_profile_for_object,
    get_place_profile_for_object,
)


class SearchResource(GrampsJSONEncoder, ProtectedResource):
    """Fulltext search resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_db_handle()

    def get_object_from_handle(
        self, handle: str, class_name: str, args: Dict, locale: GrampsLocale
    ) -> GrampsObject:
        """Get the object given a Gramps handle."""
        query_method = self.db_handle.method("get_%s_from_handle", class_name)
        assert query_method is not None  # type checker
        obj = query_method(handle)
        if obj is None:
            raise HandleError(f"Object not found for handle {handle}")
        if "profile" in args:
            if class_name == "person":
                obj.profile = get_person_profile_for_object(
                    self.db_handle,
                    obj,
                    args["profile"],
                    locale=locale,
                    name_format=args.get("name_format"),
                )
            elif class_name == "family":
                obj.profile = get_family_profile_for_object(
                    self.db_handle,
                    obj,
                    args["profile"],
                    locale=locale,
                    name_format=args.get("name_format"),
                )
            elif class_name == "event":
                obj.profile = get_event_profile_for_object(
                    self.db_handle,
                    obj,
                    args["profile"],
                    locale=locale,
                    name_format=args.get("name_format"),
                )
            elif class_name == "citation":
                obj.profile = get_citation_profile_for_object(
                    self.db_handle, obj, args["profile"], locale=locale
                )
            elif class_name == "place":
                obj.profile = get_place_profile_for_object(
                    self.db_handle, obj, locale=locale
                )
            elif class_name == "media":
                obj.profile = get_media_profile_for_object(
                    self.db_handle, obj, args["profile"], locale=locale
                )

        return obj

    @use_args(
        {
            "locale": fields.Str(
                load_default=None, validate=validate.Length(min=1, max=5)
            ),
            "query": fields.Str(required=True, validate=validate.Length(min=1)),
            "semantic": fields.Boolean(load_default=False),
            "page": fields.Int(load_default=1, validate=validate.Range(min=1)),
            "pagesize": fields.Int(load_default=20, validate=validate.Range(min=1)),
            "sort": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "profile": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(
                    choices=["all", "self", "families", "events", "age", "span"]
                ),
            ),
            "strip": fields.Boolean(load_default=False),
            "type": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(
                    choices=[t.lower() for t in PRIMARY_GRAMPS_OBJECTS]
                ),
            ),
            "change": fields.Str(validate=validate.Length(min=2)),
        },
        location="query",
    )
    def get(self, args: Dict):
        """Get search result."""
        tree = get_tree_from_jwt_or_fail()
        try:
            if args["semantic"]:
                searcher: SearchIndexer | SemanticSearchIndexer = (
                    get_semantic_search_indexer(tree)
                )
            else:
                searcher = get_search_indexer(tree)
        except ValueError:
            abort_with_message(500, "Failed initializing search")
        if args["semantic"] and args.get("sort"):
            abort_with_message(
                422, "the sort parameter is not allowed with semantic search"
            )
        if args.get("change"):
            match = re.match(r"^(<=|>=|<|>)(\d+(\.\d+)?)$", args["change"])
            if match:
                change_op: Optional[str] = match.group(1)
                change_value: Optional[float] = float(match.group(2))
            else:
                abort_with_message(422, "change parameter has invalid format")
        else:
            change_op = None
            change_value = None

        total, hits = searcher.search(
            query=args["query"],
            page=args["page"],
            pagesize=args["pagesize"],
            # search in private records if allowed to
            include_private=has_permissions([PERM_VIEW_PRIVATE]),
            sort=args.get("sort"),
            object_types=args.get("type") or None,
            change_op=change_op,
            change_value=change_value,
        )
        if hits:
            locale = get_locale_for_language(args["locale"], default=True)
            for hit in hits:
                try:
                    hit["object"] = self.get_object_from_handle(
                        handle=hit["handle"],
                        class_name=hit["object_type"],
                        args=args,
                        locale=locale,
                    )
                except HandleError:
                    pass
            # filter out hits without object (i.e. if handle failed)
            hits = [hit for hit in hits if "object" in hit]
        return self.response(200, payload=hits or [], args=args, total_items=total)


class SearchIndexResource(ProtectedResource):
    """Resource to trigger a search reindex."""

    @use_args(
        {
            "full": fields.Boolean(load_default=False),
            "semantic": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def post(self, args: Dict):
        """Trigger a reindex."""
        require_permissions([PERM_TRIGGER_REINDEX])
        tree = get_tree_from_jwt_or_fail()
        user_id = get_jwt_identity()
        if args["full"]:
            task_func = search_reindex_full
        else:
            task_func = search_reindex_incremental
        task = run_task(
            task_func, tree=tree, user_id=user_id, semantic=args["semantic"]
        )
        if isinstance(task, AsyncResult):
            return make_task_response(task)
        return Response(status=201)
