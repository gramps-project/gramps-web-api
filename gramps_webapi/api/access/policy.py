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

"""What a user may see."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Collection

from ...auth.const import PERM_VIEW_PRIVATE
from .sanitize import RawData


@dataclass(frozen=True)
class AccessPolicy:
    """Which objects of a tree a user may see.

    An object is visible if it isn't private, or if the user may view private
    objects. Private secondary objects (names, attributes, references, ...)
    are removed for users who may not view private objects.
    """

    view_private: bool

    @classmethod
    def from_permissions(cls, permissions: Collection[str]) -> AccessPolicy:
        """Return the policy for a user with these permissions."""
        return cls(view_private=PERM_VIEW_PRIVATE in permissions)

    @property
    def sees_everything(self) -> bool:
        """Whether nothing is hidden from the user."""
        return self.view_private

    def is_visible(self, data: RawData) -> bool:
        """Whether a primary object, given as raw data, is visible on its own."""
        return self.view_private or not data.get("private")

    def sql_condition(self) -> str:
        """SQL condition that is true for visible rows of a primary object table.

        Uses the `private` secondary column, which Gramps keeps in sync with
        `json_data`, so no JSON has to be parsed.
        """
        if self.view_private:
            return "1 = 1"
        return "private = 0"

    def cache_key(self) -> str:
        """Part of cache keys for responses that depend on the policy."""
        return str(int(self.view_private))
