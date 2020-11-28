"""Full-text search endpoint."""

from flask import abort, current_app, jsonify
from webargs import fields
from webargs.flaskparser import use_args

from . import ProtectedResource


class SearchResource(ProtectedResource):
    """Fulltext search resource."""

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
        return jsonify(result)
