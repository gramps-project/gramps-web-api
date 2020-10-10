"""Family API resource."""

import gramps.gen.filters.rules.family as rule_classes

from .base import (GrampsObjectProtectedResource, GrampsObjectResourceHelper,
                   GrampsObjectsProtectedResource)
from .filter import apply_filter_rules, list_filter_rules
from .util import (get_children_for_references, get_events_for_references,
                   get_family_profile_for_object, get_media_for_references,
                   get_person_by_handle)


class FamilyResourceHelper(GrampsObjectResourceHelper):
    """Family resource helper."""

    gramps_class_name = "Family"

    def object_extend(self, obj):  # pylint: disable=no-self-use
        """Extend family attributes as needed."""
        db = self.db
        if self.build_profile:
            obj.profile = get_family_profile_for_object(db, obj, with_events=True)
        if self.extend_object:
            obj.extended = {
                "children": get_children_for_references(db, obj),
                "citations": [
                    db.get_citation_from_handle(handle) for handle in obj.citation_list
                ],
                "events": get_events_for_references(db, obj),
                "father": get_person_by_handle(db, obj.father_handle),
                "media": get_media_for_references(db, obj),
                "mother": get_person_by_handle(db, obj.mother_handle),
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


class FamilyResource(GrampsObjectProtectedResource, FamilyResourceHelper):
    """Family resource."""


class FamiliesResource(GrampsObjectsProtectedResource, FamilyResourceHelper):
    """Families resource."""
