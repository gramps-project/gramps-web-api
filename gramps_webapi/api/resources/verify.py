#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

"""Data verification API resource."""

from flask import Response

from ...verify_lib import run_verify
from ...auth.const import PERM_VIEW_PRIVATE
from ..auth import require_permissions
from ..blueprint import api_blueprint
from ..util import get_db_handle
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .schemas import VerifyQueryArgs, VerifyResultSchema


class VerifyResource(ProtectedResource, GrampsJSONEncoder):
    """Data verification resource."""

    @api_blueprint.response(200, VerifyResultSchema(many=True))
    @api_blueprint.arguments(VerifyQueryArgs, location="query")
    def get(self, args) -> Response:
        """Run genealogical data verification checks against the database."""
        require_permissions([PERM_VIEW_PRIVATE])
        db = get_db_handle()
        results = run_verify(db, args)
        return self.response(200, results)
