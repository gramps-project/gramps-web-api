"""Family API resource."""

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import (
    get_father_grampsid,
    get_mother_grampsid,
    get_children_grampsids,
    get_citation_grampsids,
    get_attribute_references,
    get_event_references,
    get_media_references,
    get_note_grampsids,
    get_tag_list,
)


class FamilyResourceHelper(GrampsObjectResourceHelper):
    """Family resource helper."""

    gramps_class_name = "Family"

    def object_to_dict(self, obj):  # pylint: disable=no-self-use
        """Return the family as a dictionary."""
        db = self.db
        return {
            "gramps_id": obj.gramps_id,
            "father": get_father_grampsid(db, obj),
            "mother": get_mother_grampsid(db, obj),
            "relationship": str(obj.get_relationship()),
            "children": get_children_grampsids(db, obj),
            "attributes": get_attribute_references(db, obj),
            "events": get_event_references(db, obj),
            "citations": get_citation_grampsids(db, obj),
            "notes": get_note_grampsids(db, obj),
            "media": get_media_references(db, obj),
#            "media": [{"ref": r.ref, "rect": r.rect} for r in obj.get_media_list()],
            "tags": get_tag_list(db, obj),
            "private": obj.private,
            "change": obj.change
        }


class FamilyResource(GrampsObjectProtectedResource, FamilyResourceHelper):
    """Family resource."""


class FamiliesResource(GrampsObjectsProtectedResource, FamilyResourceHelper):
    """Families resource."""
