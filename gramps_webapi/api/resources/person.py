"""Person API resource."""

from gramps.gen.display.name import displayer as name_displayer

from .base import (GrampsObjectProtectedResource, GrampsObjectResourceHelper,
                   GrampsObjectsProtectedResource)
from .util import (get_birthdate, get_birthplace, get_deathdate,
                   get_deathplace, get_events, get_family, get_media,
                   get_people)


class PersonResourceHelper(GrampsObjectResourceHelper):
    """Person resource helper."""

    gramps_class_name = "Person"

    def object_extend(self, obj):  # pylint: disable=no-self-use
        """Extend person attributes as needed."""
        db = self.db
        obj.profile = {
            "birth_date": get_birthdate(db, obj),
            "birth_place": get_birthplace(db, obj),
            "death_date": get_deathdate(db, obj),
            "death_place": get_deathplace(db, obj),
            "name_given": name_displayer.display_given(obj),
            "name_surname": obj.primary_name.get_surname(),
        }
        if self.extend_object:
            obj.extended = {
                "citations": [
                    db.get_citation_from_handle(handle) for handle in obj.citation_list
                ],
                "events": get_events(db, obj),
                "families": [get_family(db, handle) for handle in obj.family_list],
                "parent_families": [
                    get_family(db, handle) for handle in obj.parent_family_list
                ],
                "primary_parent_family": get_family(
                    db, obj.get_main_parents_family_handle()
                ),
                "media": get_media(db, obj),
                "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
                "people": get_people(db, obj),
                "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list],
            }
        return obj


class PersonResource(GrampsObjectProtectedResource, PersonResourceHelper):
    """Person resource."""


class PeopleResource(GrampsObjectsProtectedResource, PersonResourceHelper):
    """People resource."""
