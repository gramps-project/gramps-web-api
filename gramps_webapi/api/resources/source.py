"""Source API resource."""

import gramps.gen.filters.rules.source as rule_classes

from .base import (GrampsObjectProtectedResource, GrampsObjectResourceHelper,
                   GrampsObjectsProtectedResource)
from .filter import apply_filter_rules, list_filter_rules
from .util import get_media_for_references, get_repositories_for_references


class SourceResourceHelper(GrampsObjectResourceHelper):
    """Source resource helper."""

    gramps_class_name = "Source"

    def object_extend(self, obj):
        """Extend source attributes as needed."""
        if self.extend_object:
            db = self.db
            obj.extended = {
                "media": get_media_for_references(db, obj),
                "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
                "repositories": get_repositories_for_references(db, obj),
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


class SourceResource(GrampsObjectProtectedResource, SourceResourceHelper):
    """Source resource."""


class SourcesResource(GrampsObjectsProtectedResource, SourceResourceHelper):
    """Sources resource."""
