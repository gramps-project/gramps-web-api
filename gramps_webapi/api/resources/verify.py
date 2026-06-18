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

from flask import Response, jsonify
from flask_jwt_extended import get_jwt_identity

from ...auth.const import PERM_VIEW_PRIVATE
from ..auth import require_permissions
from ..blueprint import api_blueprint
from ..tasks import AsyncResult, make_task_response, run_task, verify_database
from ..util import abort_with_message, get_tree_from_jwt_or_fail
from . import ProtectedResource
from .schemas import VerifyQueryArgs
from .trees import validate_tree_id


class VerifyResource(ProtectedResource):
    """Data verification resource."""

    @api_blueprint.arguments(VerifyQueryArgs, location="query")
    def post(self, args, tree_id: str) -> Response:
        """Run genealogical data verification checks against the database."""
        require_permissions([PERM_VIEW_PRIVATE])
        user_tree_id = get_tree_from_jwt_or_fail()
        if tree_id == "-":
            tree_id = user_tree_id
        else:
            validate_tree_id(tree_id)
            if tree_id != user_tree_id:
                abort_with_message(403, "Not allowed to verify other trees")
        user_id = get_jwt_identity()
        locale = args.pop("locale", None)
        task = run_task(
            verify_database,
            tree=tree_id,
            user_id=user_id,
            options=args or None,
            locale=locale,
        )
        if isinstance(task, AsyncResult):
            return make_task_response(task)
        return jsonify(task), 201
