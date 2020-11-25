#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
# Copyright (C) 2020      Christopher Horn
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Family API resource."""

from typing import Dict

from flask import abort
from gramps.gen.lib import Family

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


class FamilyResourceHelper(GrampsObjectResourceHelper):
    """Family resource helper."""

    gramps_class_name = "Family"

    def object_extend(self, obj: Family, args: Dict) -> Family:
        """Extend family attributes as needed."""
        db_handle = self.db_handle
        if "profile" in args:
            obj.profile = get_family_profile_for_object(db_handle, obj, args["profile"])
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
