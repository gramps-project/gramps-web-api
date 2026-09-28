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

from flask import Response, jsonify
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.lib import Place
from gramps.gen.utils.grampslocale import GrampsLocale

from ..blueprint import api_blueprint
from ..cache import request_cache_decorator
from ..util import get_db_handle
from . import ProtectedResource
from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .schemas import PlaceCoordinatesSchema
from .util import (
    get_extended_attributes,
    get_place_coordinates,
    get_place_profile_for_object,
)


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
                db_handle=db_handle,
                place=obj,
                locale=locale,
                parent_places=args.get("place_hierarchy", True),
            )
        if "extend" in args:
            obj.extended = get_extended_attributes(db_handle, obj, args)
        return obj


class PlaceResource(GrampsObjectProtectedResource, PlaceResourceHelper):
    """Place resource."""


class PlacesResource(GrampsObjectsProtectedResource, PlaceResourceHelper):
    """Places resource."""


class PlaceCoordinatesResource(ProtectedResource):
    """Place coordinates resource."""

    @api_blueprint.response(200, PlaceCoordinatesSchema(many=True))
    @request_cache_decorator
    def get(self) -> Response:
        """Get the name and coordinates of all places, in no particular order."""
        places = []
        for place in get_db_handle().iter_places():
            latitude, longitude = get_place_coordinates(place)
            places.append(
                {
                    "handle": place.handle,
                    "name": place.get_name().value,
                    "lat": latitude,
                    "long": longitude,
                }
            )
        # not self.response: GrampsJSONEncoder turns null lat/long into 0
        return jsonify(places)
