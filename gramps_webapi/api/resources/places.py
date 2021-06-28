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

"""Place API resource."""

from typing import Dict

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.lib import Place
from gramps.gen.utils.grampslocale import GrampsLocale

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import get_extended_attributes, get_place_profile_for_object


class PlaceResourceHelper(GrampsObjectResourceHelper):
    """Place resource helper."""

    gramps_class_name = "Place"

    def object_extend(
        self, obj: Place, args: Dict, locale: GrampsLocale = glocale
    ) -> Place:
        """Extend place attributes as needed."""
        db_handle = self.db_handle
        if "profile" in args:
            obj.profile = get_place_profile_for_object(
                db_handle=db_handle, place=obj, locale=locale
            )
        if "extend" in args:
            obj.extended = get_extended_attributes(db_handle, obj, args)
        return obj


class PlaceResource(GrampsObjectProtectedResource, PlaceResourceHelper):
    """Place resource."""


class PlacesResource(GrampsObjectsProtectedResource, PlaceResourceHelper):
    """Places resource."""
