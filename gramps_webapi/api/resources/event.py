"""Event API resource."""

from typing import Dict

from gramps.gen.lib import Event

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import (
    get_event_profile_for_object,
    get_extended_attributes,
    get_place_by_handle,
)


class EventResourceHelper(GrampsObjectResourceHelper):
    """Event resource helper."""

    gramps_class_name = "Event"

    def object_extend(self, obj: Event, args: Dict) -> Event:
        """Extend event attributes as needed."""
        db_handle = self.db_handle
        if "profile" in args:
            obj.profile = get_event_profile_for_object(db_handle, obj)
        if "extend" in args:
            obj.extended = get_extended_attributes(db_handle, obj, args)
            if "all" in args["extend"] or "place" in args["extend"]:
                obj.extended["place"] = get_place_by_handle(db_handle, obj.place)
        return obj


class EventResource(GrampsObjectProtectedResource, EventResourceHelper):
    """Event resource."""


class EventsResource(GrampsObjectsProtectedResource, EventResourceHelper):
    """Events resource."""
