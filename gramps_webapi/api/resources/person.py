"""Person API resource."""

from gramps.gen.display.name import displayer as name_displayer

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import (
    get_birthdate,
    get_birthplace_handle,
    get_deathdate,
    get_deathplace_handle,
    get_alternate_names,
    get_attributes,
    get_event_references,
    get_media_references,
    get_person_references,
    get_urls,
    get_lds_events
)


class PersonResourceHelper(GrampsObjectResourceHelper):
    """Person resource helper."""

    gramps_class_name = "Person"

    def object_to_dict(self, obj):  # pylint: disable=no-self-use
        """Return the person as a dictionary."""
        db = self.db
        return {
            "alternate_names": get_alternate_names(obj),
            "associations": get_person_references(obj),
            "attributes": get_attributes(obj),
            "birth_date": get_birthdate(db, obj),
            "birth_indicator": obj.birth_ref_index,
            "birth_place": get_birthplace_handle(db, obj),
            "change": obj.change,
            "citations": obj.get_citation_list(),
            "death_date": get_deathdate(db, obj),
            "death_indicator": obj.death_ref_index,
            "death_place": get_deathplace_handle(db, obj),
            "events": get_event_references(obj),
            "families": obj.get_family_handle_list(),
            "gender": obj.gender,
            "gramps_id": obj.gramps_id,
            "handle": obj.handle,
            "lds": get_lds_events(obj),
            "media": get_media_references(obj),
            "name_given": name_displayer.display_given(obj),
            "name_surname": obj.primary_name.get_surname(),
            "notes": obj.get_note_list(),
            "parents": obj.get_parent_family_handle_list(),
            "parents_primary": obj.get_main_parents_family_handle(),
            "private": obj.private,
            "tags": obj.get_tag_list(),
            "urls": get_urls(obj)
        }


class PersonResource(GrampsObjectProtectedResource, PersonResourceHelper):
    """Person resource."""


class PeopleResource(GrampsObjectsProtectedResource, PersonResourceHelper):
    """People resource."""
