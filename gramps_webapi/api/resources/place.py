"""Place API resource."""

import gramps.gen.filters.rules.place as rule_classes

from .base import (GrampsObjectProtectedResource, GrampsObjectResourceHelper,
                   GrampsObjectsProtectedResource)
from .filter import apply_filter_rules, list_filter_rules
from .util import get_media_for_references


class PlaceResourceHelper(GrampsObjectResourceHelper):
    """Place resource helper."""

    gramps_class_name = "Place"

    def object_extend(self, obj):
        """Extend place attributes as needed."""
        if self.extend_object:
            db = self.db
            obj.extended = {
                "citations": [
                    db.get_citation_from_handle(handle) for handle in obj.citation_list
                ],
                "media": get_media_for_references(db, obj),
                "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
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


class PlaceResource(GrampsObjectProtectedResource, PlaceResourceHelper):
    """Place resource."""


class PlacesResource(GrampsObjectsProtectedResource, PlaceResourceHelper):
    """Places resource."""
