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

# import json
from http import HTTPStatus

from celery.result import AsyncResult
from flask import abort
from gramps.gen.lib.json_utils import object_to_string

from . import ProtectedResource


class TaskResource(ProtectedResource):
    """Resource for a single task."""

    def get(self, task_id: str):
        """Get info about a task."""
        task = AsyncResult(task_id)
        if task is None:
            abort(HTTPStatus.NOT_FOUND)

        def serialize_or_str(obj):
            try:
                return object_to_string(obj)  # json.dumps(obj)
            except TypeError:
                return str(obj)

        def serializable_or_str(obj):
            try:
                # json.dumps(obj)
                object_to_string(obj)
                return obj
            except TypeError:
                return str(obj)

        return {
            "state": task.state,
            "result_object": serializable_or_str(task.result),
            # kept for backward compatibility
            "info": serialize_or_str(task.info),
            "result": serialize_or_str(task.result),
        }
