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
    get_media_for_references,
    get_place_by_handle,
)


class EventResourceHelper(GrampsObjectResourceHelper):
    """Event resource helper."""

    gramps_class_name = "Event"

    def object_extend(self, obj: Event, args: Dict) -> Event:
        """Extend event attributes as needed."""
        db = self.db
        if args["profile"]:
            obj.profile = get_event_profile_for_object(db, obj)
        if args["extend"]:
            obj.extended = {
                "citations": [
                    db.get_citation_from_handle(handle) for handle in obj.citation_list
                ],
                "media": get_media_for_references(db, obj),
                "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
                "place": get_place_by_handle(db, obj.place),
                "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list],
            }
        return obj


class EventResource(GrampsObjectProtectedResource, EventResourceHelper):
    """Event resource."""


class EventsResource(GrampsObjectsProtectedResource, EventResourceHelper):
    """Events resource."""
