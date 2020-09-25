"""Person API resource."""

from gramps.gen.display.name import displayer as name_displayer

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import (
    get_birthdate,
    get_birthplace_grampsid,
    get_citation_grampsids,
    get_deathdate,
    get_deathplace_grampsid,
    get_event_grampsids_roles,
    get_families_grampsids,
    get_note_grampsids,
    get_parents_grampsids,
)


class PersonResourceHelper(GrampsObjectResourceHelper):
    """Person resource helper."""

    gramps_class_name = "Person"

    def object_to_dict(self, obj):  # pylint: disable=no-self-use
        """Return the person as a dictionary."""
        db = self.db
        return {
            "gramps_id": obj.gramps_id,
            "name_given": name_displayer.display_given(obj),
            "name_surname": obj.primary_name.get_surname(),
            "gender": obj.gender,
            "birthdate": get_birthdate(db, obj),
            "deathdate": get_deathdate(db, obj),
            "birthplace": get_birthplace_grampsid(db, obj),
            "deathplace": get_deathplace_grampsid(db, obj),
            "parents": get_parents_grampsids(db, obj),
            "families": get_families_grampsids(db, obj),
            "events": get_event_grampsids_roles(db, obj),
            "media": [{"ref": r.ref, "rect": r.rect} for r in obj.get_media_list()],
            "citations": get_citation_grampsids(db, obj),
            "notes": get_note_grampsids(db, obj),
        }


class PersonResource(GrampsObjectProtectedResource, PersonResourceHelper):
    """Person resource."""


class PeopleResource(GrampsObjectsProtectedResource, PersonResourceHelper):
    """People resource."""
