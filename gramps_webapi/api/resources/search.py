"""Full-text search endpoint."""

from flask import current_app
from gramps.gen.db.base import DbReadBase
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from webargs import fields
from webargs.flaskparser import use_args

from ..util import get_dbstate
from . import ProtectedResource
from .emit import GrampsJSONEncoder


class SearchResource(GrampsJSONEncoder, ProtectedResource):
    """Fulltext search resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get_object_from_handle(self, handle: str, class_name: str) -> GrampsObject:
        """Get the object given a Gramps handle."""
        query_method = self.db_handle.method("get_%s_from_handle", class_name)
        return query_method(handle)

    @use_args(
        {
            "query": fields.Str(required=True),
            "page": fields.Int(missing=1, required=False),
            "pagesize": fields.Int(missing=10, required=False),
        },
        location="query",
    )
    def get(self, args):
        """Get search result."""
        searcher = current_app.config["SEARCH_INDEXER"]
        result = searcher.search(args["query"], args["page"], args["pagesize"])
        if "hits" in result:
            for hit in result["hits"]:
                hit["object"] = self.get_object_from_handle(
                    handle=hit["handle"], class_name=hit["object_type"]
                )
        return self.response(200, payload=result)
