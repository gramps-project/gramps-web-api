"""Event API resource."""

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)


class EventResourceHelper(GrampsObjectResourceHelper):
    """Event resource helper."""

    gramps_class_name = "Event"

    def object_denormalize(self, obj):
        """Denormalize event attributes if needed."""
        return obj

    
class EventResource(GrampsObjectProtectedResource, EventResourceHelper):
    """Event resource."""


class EventsResource(GrampsObjectsProtectedResource, EventResourceHelper):
    """Events resource."""
