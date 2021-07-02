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

from typing import Dict

from flask import current_app
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from gramps.gen.utils.grampslocale import GrampsLocale
from webargs import fields, validate

from ...auth.const import PERM_VIEW_PRIVATE
from ..auth import has_permissions
from ..util import get_db_handle, get_locale_for_language, use_args
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .util import (
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
        obj = query_method(handle)
        if "profile" in args:
            if class_name == "person":
                obj.profile = get_person_profile_for_object(
                    self.db_handle, obj, args["profile"], locale=locale
                )
            elif class_name == "family":
                obj.profile = get_family_profile_for_object(
                    self.db_handle, obj, args["profile"], locale=locale
                )
            elif class_name == "event":
                obj.profile = get_event_profile_for_object(
                    self.db_handle, obj, args["profile"], locale=locale
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
            "locale": fields.Str(missing=None, validate=validate.Length(min=1, max=5)),
            "query": fields.Str(required=True, validate=validate.Length(min=1)),
            "page": fields.Int(missing=1, validate=validate.Range(min=1)),
            "pagesize": fields.Int(missing=20, validate=validate.Range(min=1)),
            "sort": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "profile": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(
                    choices=["all", "self", "families", "events", "age", "span"]
                ),
            ),
            "strip": fields.Boolean(missing=False),
        },
        location="query",
    )
    def get(self, args: Dict):
        """Get search result."""
        searcher = current_app.config["SEARCH_INDEXER"]
        total, hits = searcher.search(
            query=args["query"],
            page=args["page"],
            pagesize=args["pagesize"],
            # search in private records if allowed to
            include_private=has_permissions([PERM_VIEW_PRIVATE]),
            sort=args.get("sort"),
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
