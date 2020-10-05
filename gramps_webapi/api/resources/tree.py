"""Tree API resource."""

from flask import Response, abort
from gramps.gen.db.base import DbReadBase
from webargs import fields
from webargs.flaskparser import use_args

from ..util import get_dbstate
from . import ProtectedResource, Resource
from .emit import GrampsJSONEncoder


class TreeResource(ProtectedResource, GrampsJSONEncoder):
    """Tree resource."""

    @property
    def db(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    @use_args(
        {
            "surnames": fields.Boolean()
        },
        location="query",
    )
    def get(self, args):
        """Get tree related information."""
        db = self.db

        result = {
            "default_person": db.get_default_handle(),
            "mediapath": db.get_mediapath(),
            "researcher": db.get_researcher(),
            "savepath": db.get_save_path(),
            "summary": db.get_summary(),
        }
        if 'surnames' in args:
            result.update({'surnames': db.get_surname_list()})

        return Response(
            response=self.encode(result),
            status=200,
            mimetype="application/json",
        )
