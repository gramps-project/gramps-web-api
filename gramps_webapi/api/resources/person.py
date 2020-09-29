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
    get_main_parents_grampsids,
    get_parents_grampsids,
    get_families_grampsids,
    get_event_references,
    get_attribute_references,
    get_media_references,
    get_note_grampsids,
    get_tag_list,
    get_alternate_names,
    get_person_associations
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
            "alternate_names": get_alternate_names(db, obj),
            "gender": obj.gender,
            "birthdate": get_birthdate(db, obj),
            "deathdate": get_deathdate(db, obj),
            "birthplace": get_birthplace_grampsid(db, obj),
            "deathplace": get_deathplace_grampsid(db, obj),
            "birth_ref_index": obj.birth_ref_index,
            "death_ref_index": obj.death_ref_index,
            "main_parents": get_main_parents_grampsids(db, obj),
            "parents": get_parents_grampsids(db, obj),
            "families": get_families_grampsids(db, obj),
            "attributes": get_attribute_references(db, obj),
            "events": get_event_references(db, obj),
            "associations": get_person_associations(db, obj),
            "citations": get_citation_grampsids(db, obj),
            "notes": get_note_grampsids(db, obj),
            "media": get_media_references(db, obj),
            "tags": get_tag_list(db, obj),
            "private": obj.private,
            "change": obj.change,
        }


class PersonResource(GrampsObjectProtectedResource, PersonResourceHelper):
    """Person resource."""


class PeopleResource(GrampsObjectsProtectedResource, PersonResourceHelper):
    """People resource."""
