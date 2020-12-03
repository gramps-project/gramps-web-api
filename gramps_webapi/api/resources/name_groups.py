#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
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

"""Name Groups API resource."""

from flask import Response, abort
from gramps.gen.db.base import DbReadBase

from ..util import get_db_handle
from . import ProtectedResource
from .emit import GrampsJSONEncoder


class NameGroupsResource(ProtectedResource, GrampsJSONEncoder):
    """Name group mappings resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_db_handle()

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
