"""Metadata API resource."""

from typing import Dict

from flask import Response, abort
from gramps.gen.db.base import DbReadBase
from webargs import fields
from webargs.flaskparser import use_args

from ..util import get_dbstate
from . import ProtectedResource
from .emit import GrampsJSONEncoder


class MetadataResource(ProtectedResource, GrampsJSONEncoder):
    """Metadata resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    @use_args(
        {"type": fields.Str()},
        location="query",
    )
    def get(self, args: Dict, datatype: str) -> Response:
        """Get tree or application related metadata information."""
        db_handle = self.db_handle
        if datatype == "summary":
            summary = {}
            data = db_handle.get_summary()
            for item in data:
                summary[item.replace(" ", "_").lower()] = data[item]
            return self.response(200, summary)
        if datatype == "researcher":
            return self.response(200, db_handle.get_researcher())
        if datatype == "surnames":
            return self.response(200, db_handle.get_surname_list())
        abort(404)
