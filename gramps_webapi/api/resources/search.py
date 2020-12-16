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

"""Full-text search endpoint."""

from typing import Dict

from flask import current_app
from gramps.gen.db.base import DbReadBase
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from gramps.gen.utils.grampslocale import GrampsLocale
from webargs import fields, validate

from ..util import use_args
from ..util import get_db_handle, get_locale_for_language
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .util import (
    get_event_profile_for_object,
    get_family_profile_for_object,
    get_person_profile_for_object,
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
                    self.db_handle, obj, locale=locale
                )
        return obj

    @use_args(
        {
            "locale": fields.Str(missing=None, validate=validate.Length(min=1, max=5)),
            "query": fields.Str(required=True, validate=validate.Length(min=1)),
            "page": fields.Int(missing=1, validate=validate.Range(min=1)),
            "pagesize": fields.Int(missing=20, validate=validate.Range(min=1)),
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
        total, hits = searcher.search(args["query"], args["page"], args["pagesize"])
        if hits:
            locale = get_locale_for_language(args["locale"], default=True)
            for hit in hits:
                hit["object"] = self.get_object_from_handle(
                    handle=hit["handle"],
                    class_name=hit["object_type"],
                    args=args,
                    locale=locale,
                )
        return self.response(200, payload=hits or [], args=args, total_items=total)
