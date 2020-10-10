"""Note API resource."""

import gramps.gen.filters.rules.note as rule_classes

from .base import (GrampsObjectProtectedResource, GrampsObjectResourceHelper,
                   GrampsObjectsProtectedResource)
from .filter import apply_filter_rules, list_filter_rules


class NoteResourceHelper(GrampsObjectResourceHelper):
    """Note resource helper."""

    gramps_class_name = "Note"

    def object_extend(self, obj):
        """Extend note attributes as needed."""
        if self.extend_object:
            db = self.db
            obj.extended = {
                "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list]
            }
        return obj

    def object_filter_rules(self):
        """Build and return list of filter rules."""
        return list_filter_rules(rule_classes)

    def object_filter(self, args):
        """Build and apply a filter."""
        db = self.db
        return apply_filter_rules(db, args, rule_classes)


class NoteResource(GrampsObjectProtectedResource, NoteResourceHelper):
    """Note resource."""


class NotesResource(GrampsObjectsProtectedResource, NoteResourceHelper):
    """Notes resource."""
