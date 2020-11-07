"""Name Groups API resource."""

from flask import Response, abort
from gramps.gen.db.base import DbReadBase

from ..util import get_dbstate
from . import ProtectedResource
from .emit import GrampsJSONEncoder


class NameGroupsResource(ProtectedResource, GrampsJSONEncoder):
    """Name group mappings resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get(self, surname: str = None) -> Response:
        """Get list of name group mappings."""
        db_handle = self.db_handle
        if surname is not None:
            return self.response(
                200,
                {
                    "surname": surname,
                    "group": db_handle.get_name_group_mapping(surname),
                },
            )
        result = db_handle.get_name_group_keys()
        mappings = []
        if result is not None:
            for name in result:
                mappings.append(
                    {"surname": name, "group": db_handle.get_name_group_mapping(name)}
                )
        return self.response(200, mappings)

    def post(self, surname: str = None, group: str = None) -> Response:
        """Set a name group mapping."""
        db_handle = self.db_handle
        if surname is None or group is None or len(surname) == 0 or len(group) == 0:
            abort(400)
        db_handle.set_name_group_mapping(surname, group)
        return self.response(201, {"surname": surname, "group": group})
