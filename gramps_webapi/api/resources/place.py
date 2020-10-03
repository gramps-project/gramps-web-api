"""Place API resource."""

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)


class PlaceResourceHelper(GrampsObjectResourceHelper):
    """Place resource helper."""

    gramps_class_name = "Place"

    def object_denormalize(self, obj):
        """Denormalize place attributes if needed."""
        return obj

    
class PlaceResource(GrampsObjectProtectedResource, PlaceResourceHelper):
    """Place resource."""


class PlacesResource(GrampsObjectsProtectedResource, PlaceResourceHelper):
    """Places resource."""
