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
    abort_with_message,
    check_quota_ai,
    update_usage_ai,
)
from ..blueprint import api_blueprint
from ..tasks import AsyncResult, make_task_response, process_chat, run_task
from . import ProtectedResource
from .schemas import ChatResponseSchema
from ...auth.const import PERM_USE_CHAT, PERM_VIEW_PRIVATE
from ..auth import has_permissions, require_permissions


class ChatMessageSchema(Schema):
    role = fields.Str(
        required=True,
        metadata={
            "description": "Role of the message sender: one of 'human', 'ai', 'system', 'assistant', or 'error'."
        },
    )
    message = fields.Str(
        required=True,
        metadata={"description": "The message content."},
    )


class ChatBodyArgs(Schema):
    """Body arguments for POST /chat/."""

    query = fields.Str(
        required=True,
        metadata={"description": "The chat prompt to answer."},
    )
    history = fields.List(
        fields.Nested(ChatMessageSchema),
        required=False,
        metadata={
            "description": "Optional list of prior conversation messages ({role, message})."
        },
    )


class ChatQueryArgs(Schema):
    """Query arguments for POST /chat/."""

    background = fields.Boolean(
        load_default=False,
        metadata={
            "description": "If true, process the chat in the background and return HTTP 202."
        },
    )
    verbose = fields.Boolean(
        load_default=False,
        metadata={
            "description": "If true, include detailed agent metadata (tool calls, token usage) in the response."
        },
    )


class ChatResource(ProtectedResource):
    """AI chat resource."""

    @api_blueprint.response(200, ChatResponseSchema())
    @api_blueprint.arguments(ChatBodyArgs, location="json")
    @api_blueprint.arguments(ChatQueryArgs, location="query")
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
