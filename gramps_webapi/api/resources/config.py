#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2022      David Straub
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

"""User administration resources."""


from flask import abort, current_app, jsonify
from webargs import fields

from ...auth import config_delete, config_get, config_get_all, config_set
from ...auth.const import PERM_EDIT_SETTINGS, PERM_VIEW_SETTINGS
from ...const import DB_CONFIG_ALLOWED_KEYS
from ..auth import require_permissions
from ..util import use_args
from . import ProtectedResource


class ConfigsResource(ProtectedResource):
    """Resource for configuration settings."""

    def get(self):
        """Get all config settings."""
        require_permissions([PERM_VIEW_SETTINGS])
        return jsonify(config_get_all()), 200


class ConfigResource(ProtectedResource):
    """Resource for a single config setting."""

    def get(self, key: str):
        """Get a config setting."""
        require_permissions([PERM_VIEW_SETTINGS])
        if key not in DB_CONFIG_ALLOWED_KEYS:
            abort(404)
        val = config_get(key)
        if val is None:
            abort(404)
        return jsonify(val), 200

    @use_args(
        {
            "value": fields.Str(required=True),
        },
        location="json",
    )
    def put(self, args, key: str):
        """Update a config setting."""
        require_permissions([PERM_EDIT_SETTINGS])
        try:
            config_set(key=key, value=args["value"])
        except ValueError:
            abort(404)  # key not allowed
        return "", 200

    def delete(self, key: str):
        """Delete a config setting."""
        require_permissions([PERM_EDIT_SETTINGS])
        try:
            if config_get(key=key) is None:
                abort(404)
        except ValueError:
            abort(404)
        config_delete(key=key)
        return "", 200
