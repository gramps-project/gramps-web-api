"""Family API resource."""

from .base import (GrampsObjectProtectedResource, GrampsObjectResourceHelper,
                   GrampsObjectsProtectedResource)
from .util import (get_children, get_events, get_media, get_people,
                   get_person_by_handle)


class FamilyResourceHelper(GrampsObjectResourceHelper):
    """Family resource helper."""

    gramps_class_name = "Family"

    def object_extend(self, obj):  # pylint: disable=no-self-use
        """Extend family attributes as needed."""
        if self.extend_object:
            db = self.db
            obj.extended = {
                "children": get_children(db, obj),
                "citations": [
                    db.get_citation_from_handle(handle) for handle in obj.citation_list
                ],
                "events": get_events(db, obj),
                "father": get_person_by_handle(db, obj.father_handle),
                "media": get_media(db, obj),
                "mother": get_person_by_handle(db, obj.mother_handle),
                "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
                "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list],
            }
        return obj


class FamilyResource(GrampsObjectProtectedResource, FamilyResourceHelper):
    """Family resource."""


class FamiliesResource(GrampsObjectsProtectedResource, FamilyResourceHelper):
    """Families resource."""
