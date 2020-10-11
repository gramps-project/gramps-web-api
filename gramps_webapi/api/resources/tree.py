"""Tree API resource."""

from typing import Dict

from flask import Response
from gramps.gen.db.base import DbReadBase
from webargs import fields
from webargs.flaskparser import use_args

from ..util import get_dbstate
from . import ProtectedResource
from .emit import GrampsJSONEncoder


class TreeResource(ProtectedResource, GrampsJSONEncoder):
    """Tree resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    @use_args(
        {"surnames": fields.Boolean(missing=False)},
        location="query",
    )
    def get(self, args: Dict) -> Response:
        """Get tree related information."""
        db_handle = self.db_handle
        result = {
            "default_person": db_handle.get_default_handle(),
            "mediapath": db_handle.get_mediapath(),
            "researcher": db_handle.get_researcher(),
            "savepath": db_handle.get_save_path(),
            "summary": db_handle.get_summary(),
        }
        if args["surnames"]:
            result.update({"surnames": db_handle.get_surname_list()})

        return self.response(result)
