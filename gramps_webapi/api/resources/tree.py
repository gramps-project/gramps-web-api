"""Tree API resource."""

from flask import Response, abort
from gramps.gen.db.base import DbReadBase

from ..util import get_dbstate
from . import ProtectedResource, Resource
from .emit import GrampsJSONEncoder


class TreeResource(ProtectedResource, GrampsJSONEncoder):
    """Tree resource."""

    @property
    def db(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get(self):
        """Get tree related information."""
        db = self.db

        result = {
            "default_person": db.get_default_handle(),
            "mediapath": db.get_mediapath(),
            "researcher": db.get_researcher(),
            "savepath": db.get_save_path(),
            "summary": db.get_summary(),
        }

        return Response(
            response=self.encode(result),
            status=200,
            mimetype="application/json",
        )
