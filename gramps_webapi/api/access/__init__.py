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
#

"""Read access control.

`AccessPolicy` decides what a user may see, and `RestrictedDb` applies it to
everything read from a tree. View functions and genealogical helpers get a
`RestrictedDb` and never check permissions themselves.
"""

from .db import RestrictedDb
from .policy import AccessPolicy

__all__ = ["AccessPolicy", "RestrictedDb"]
