"""Event API resource."""

import gramps.gen.filters.rules.event as rule_classes

from .base import (GrampsObjectProtectedResource, GrampsObjectResourceHelper,
                   GrampsObjectsProtectedResource)
from .filter import apply_filter_rules, list_filter_rules
from .util import (get_event_profile_for_object, get_media_for_references,
                   get_place_by_handle)


class EventResourceHelper(GrampsObjectResourceHelper):
    """Event resource helper."""

    gramps_class_name = "Event"

    def object_extend(self, obj):
        """Extend event attributes as needed."""
        db = self.db
        if self.build_profile:
            obj.profile = get_event_profile_for_object(db, obj)
        if self.extend_object:
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

    def object_filter_rules(self):
        """Build and return list of filter rules."""
        return list_filter_rules(rule_classes)

    def object_filter(self, args):
        """Build and apply a filter."""
        db = self.db
        return apply_filter_rules(db, args, rule_classes)


class EventResource(GrampsObjectProtectedResource, EventResourceHelper):
    """Event resource."""


class EventsResource(GrampsObjectsProtectedResource, EventResourceHelper):
    """Events resource."""
