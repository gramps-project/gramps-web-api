#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Name Formats API resource."""

from flask import Response
from gramps.gen.db.base import DbReadBase

from ..util import get_db_handle
from . import ProtectedResource
from .emit import GrampsJSONEncoder


class NameFormatsResource(ProtectedResource, GrampsJSONEncoder):
    """Name Formats resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_db_handle()

    def get(self) -> Response:
        """Get list of name formats."""
        formats = []
        for number, name, format_string, active in self.db_handle.name_formats:
            formats.append(
                {
                    "number": number,
                    "name": name,
                    "format": format_string,
                    "active": active,
                }
            )
        return self.response(200, formats)
