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
from webargs import fields
from webargs.flaskparser import use_args

from ..util import get_db_handle
from . import ProtectedResource
from .emit import GrampsJSONEncoder


class SearchResource(GrampsJSONEncoder, ProtectedResource):
    """Fulltext search resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_db_handle()

    def get_object_from_handle(self, handle: str, class_name: str) -> GrampsObject:
        """Get the object given a Gramps handle."""
        query_method = self.db_handle.method("get_%s_from_handle", class_name)
        return query_method(handle)

    @use_args(
        {
            "query": fields.Str(required=True),
            "page": fields.Int(missing=1, required=False),
            "pagesize": fields.Int(missing=20, required=False),
        },
        location="query",
    )
    def get(self, args: Dict):
        """Get search result."""
        searcher = current_app.config["SEARCH_INDEXER"]
        total, hits = searcher.search(args["query"], args["page"], args["pagesize"])
        if hits:
            for hit in hits:
                hit["object"] = self.get_object_from_handle(
                    handle=hit["handle"], class_name=hit["object_type"]
                )
        return self.response(200, payload=hits, total_items=total)
