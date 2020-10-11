"""Place API resource."""

from typing import Dict

from gramps.gen.lib import Place

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import get_extended_attributes


class PlaceResourceHelper(GrampsObjectResourceHelper):
    """Place resource helper."""

    gramps_class_name = "Place"

    def object_extend(self, obj: Place, args: Dict) -> Place:
        """Extend place attributes as needed."""
        if args["extend"]:
            db_handle = self.db_handle
            obj.extended = get_extended_attributes(db_handle, obj)
        return obj


class PlaceResource(GrampsObjectProtectedResource, PlaceResourceHelper):
    """Place resource."""


class PlacesResource(GrampsObjectsProtectedResource, PlaceResourceHelper):
    """Places resource."""
