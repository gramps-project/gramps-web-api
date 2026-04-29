#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2023      David Straub
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

"""Background task resources."""

from http import HTTPStatus

from celery.result import AsyncResult
from flask import abort
from flask_jwt_extended import get_jwt_identity
from gramps.gen.lib.json_utils import object_to_string
from marshmallow import Schema
from webargs import fields

from ...auth import TaskTree, user_db
from ...auth.const import PERM_VIEW_OTHER_USER
from ..auth import has_permissions
from ..blueprint import api_blueprint
from ..util import get_tree_from_jwt_or_fail
from . import ProtectedResource


class TaskStatusSchema(Schema):
    """Response schema for GET /tasks/<task_id>."""

    state = fields.Str(
        metadata={
            "description": "The current task state"
            " (e.g. 'PENDING', 'STARTED', 'SUCCESS', 'FAILURE')."
        },
    )
    result_object = fields.Raw(
        metadata={"description": "The task result object if available."},
    )
    info = fields.Str(
        metadata={"description": "Human-readable status information."},
    )
    result = fields.Str(
        metadata={"description": "The task result as a string."},
    )
    # Extended fields from task_tree — absent for tasks dispatched before migration
    task_id = fields.Str(
        dump_default=None,
        metadata={"description": "The Celery task UUID."},
    )
    name = fields.Str(
        dump_default=None,
        metadata={"description": "Celery task function name, e.g. 'import_file'."},
    )
    created_at = fields.DateTime(
        dump_default=None,
        metadata={"description": "UTC timestamp when the task was dispatched."},
    )
    user_id = fields.Str(
        dump_default=None,
        metadata={"description": "UUID of the user who dispatched the task."},
    )


class TaskListItemSchema(Schema):
    """Response schema for a single item in GET /tasks/."""

    task_id = fields.Str(
        metadata={"description": "The Celery task UUID."},
    )
    name = fields.Str(
        metadata={"description": "Celery task function name, e.g. 'import_file'."},
    )
    created_at = fields.DateTime(
        metadata={"description": "UTC timestamp when the task was dispatched."},
    )
    user_id = fields.Str(
        dump_default=None,
        metadata={"description": "UUID of the user who dispatched the task."},
    )
    state = fields.Str(
        dump_default=None,
        metadata={
            "description": "The current task state"
            " (e.g. 'PENDING', 'STARTED', 'SUCCESS', 'FAILURE')."
            " Only populated when include_state=true."
        },
    )


class TaskListArgsSchema(Schema):
    """Query args for GET /tasks/."""

    include_state = fields.Bool(
        load_default=False,
        metadata={
            "description": "Fetch live state from Celery backend for each task."
            " Adds one backend call per task."
        },
    )
    limit = fields.Int(
        load_default=100,
        metadata={"description": "Maximum number of tasks to return (default 100)."},
    )


def _serialize_task_result(obj):
    try:
        return object_to_string(obj)
    except TypeError:
        return str(obj)


def _serializable_task_result(obj):
    try:
        object_to_string(obj)
        return obj
    except TypeError:
        return str(obj)


class TaskResource(ProtectedResource):
    """Resource for a single task."""

    @api_blueprint.response(200, TaskStatusSchema)
    def get(self, task_id: str):
        """Get info about a task."""
        task = AsyncResult(task_id)
        if task is None:
            abort(HTTPStatus.NOT_FOUND)

        row = user_db.session.get(TaskTree, task_id)
        if row is not None:
            tree = get_tree_from_jwt_or_fail()
            if row.tree != tree:
                abort(HTTPStatus.FORBIDDEN)

        result = {
            "state": task.state,
            "result_object": _serializable_task_result(task.result),
            # kept for backward compatibility
            "info": _serialize_task_result(task.info),
            "result": _serialize_task_result(task.result),
        }
        if row is not None:
            result["task_id"] = row.task_id
            result["name"] = row.name
            result["created_at"] = row.created_at
            result["user_id"] = row.user_id
        return result


class TaskListResource(ProtectedResource):
    """Resource for listing tasks for the current tree."""

    @api_blueprint.response(200, TaskListItemSchema(many=True))
    @api_blueprint.arguments(TaskListArgsSchema, location="query")
    def get(self, args):
        """List tasks for the current tree.

        Any authenticated user can see their own tasks. Users with the
        ViewOtherUser permission (Owner+) can see all tasks for the tree.
        """
        tree = get_tree_from_jwt_or_fail()
        query = user_db.session.query(TaskTree).filter(TaskTree.tree == tree)
        if not has_permissions([PERM_VIEW_OTHER_USER]):
            query = query.filter(TaskTree.user_id == get_jwt_identity())
        rows = (
            query.order_by(TaskTree.created_at.desc()).limit(args["limit"]).all()
        )
        return [
            {
                "task_id": row.task_id,
                "name": row.name,
                "created_at": row.created_at,
                "user_id": row.user_id,
                "state": (AsyncResult(row.task_id).state or "PENDING")
                if args["include_state"]
                else None,
            }
            for row in rows
        ]
