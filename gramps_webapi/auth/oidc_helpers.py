#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025           Alexander Bocken
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

"""OIDC helper functions that must be in a separate module to avoid circular imports.

This module contains only the minimal set of functions needed by other modules
before oidc.py is fully initialized. It must not import from api modules.
"""

from flask import current_app


def is_oidc_enabled() -> bool:
    """Check if OIDC is enabled in the current app."""
    return current_app.config.get("OIDC_ENABLED", False)
