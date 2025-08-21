#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
# Copyright (C) 2020      Christopher Horn
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

"""Family API resource."""

from typing import Dict

from flask import Response, abort
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.lib import Family
from gramps.gen.utils.grampslocale import GrampsLocale

from ...auth.const import PERM_ADD_OBJ, PERM_EDIT_OBJ
from ..auth import require_permissions
from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import (
    get_extended_attributes,
    get_family_profile_for_object,
    get_person_by_handle,
)
from gramps_webapi.types import ResponseReturnValue


class FamilyResourceHelper(GrampsObjectResourceHelper):
    """Family resource helper."""

    gramps_class_name = "Family"

    def object_extend(
        self, obj: Family, args: Dict, locale: GrampsLocale = glocale
    ) -> Family:
        """Extend family attributes as needed."""
        db_handle = self.db_handle
        if "profile" in args:
            obj.profile = get_family_profile_for_object(
                db_handle,
                obj,
                args["profile"],
                locale=locale,
                name_format=args.get("name_format"),
            )
        if "extend" in args:
            obj.extended = get_extended_attributes(db_handle, obj, args)
            if "all" in args["extend"] or "father_handle" in args["extend"]:
                obj.extended["father"] = get_person_by_handle(
                    db_handle, obj.father_handle
                )
            if "all" in args["extend"] or "mother_handle" in args["extend"]:
                obj.extended["mother"] = get_person_by_handle(
                    db_handle, obj.mother_handle
                )
        return obj


class FamilyResource(GrampsObjectProtectedResource, FamilyResourceHelper):
    """Family resource."""


class FamiliesResource(GrampsObjectsProtectedResource, FamilyResourceHelper):
    """Families resource."""

    def post(self) -> ResponseReturnValue:
        """Post a new object.

        The parent class's method is overridden since creating a Family object
        modifies the family members' Person objects as well, so `PERM_EDIT_OBJ`
        is required.
        """
        require_permissions([PERM_ADD_OBJ, PERM_EDIT_OBJ])
        return GrampsObjectsProtectedResource.post(self)
