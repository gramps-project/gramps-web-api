#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2024      David Straub
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

"""AI chat endpoint."""

from flask_jwt_extended import get_jwt_identity
from marshmallow import Schema
from webargs import fields

from ..util import (
    get_tree_from_jwt_or_fail,
    use_args,
    abort_with_message,
    check_quota_ai,
    update_usage_ai,
)
from ..tasks import AsyncResult, make_task_response, process_chat, run_task
from . import ProtectedResource
from ...auth.const import PERM_USE_CHAT, PERM_VIEW_PRIVATE
from ..auth import has_permissions, require_permissions


class ChatMessageSchema(Schema):
    role = fields.Str(required=True)
    message = fields.Str(required=True)


class ChatResource(ProtectedResource):
    """AI chat resource."""

    @use_args(
        {
            "query": fields.Str(required=True),
            "history": fields.List(fields.Nested(ChatMessageSchema), required=False),
        },
        location="json",
    )
    @use_args(
        {
            "background": fields.Boolean(load_default=False),
            "verbose": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def post(self, args_json, args_query):
        """Create a chat response."""
        require_permissions({PERM_USE_CHAT})
        check_quota_ai(requested=1)
        tree = get_tree_from_jwt_or_fail()
        user_id = get_jwt_identity()
        include_private = has_permissions({PERM_VIEW_PRIVATE})

        if args_query["background"]:
            task = run_task(
                process_chat,
                tree=tree,
                user_id=user_id,
                query=args_json["query"],
                include_private=include_private,
                history=args_json.get("history"),
                verbose=args_query["verbose"],
            )
            if isinstance(task, AsyncResult):
                return make_task_response(task)
            update_usage_ai(new=1)
            return task, 200

        try:
            result = process_chat(
                tree=tree,
                user_id=user_id,
                query=args_json["query"],
                include_private=include_private,
                history=args_json.get("history"),
                verbose=args_query["verbose"],
            )
        except ValueError:
            abort_with_message(422, "Invalid message format")

        update_usage_ai(new=1)
        return result
