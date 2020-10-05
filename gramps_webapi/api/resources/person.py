"""Person API resource."""

import json

from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.lib.serialize import to_json

from .base import (GrampsObjectProtectedResource, GrampsObjectResourceHelper,
                   GrampsObjectsProtectedResource)
from .util import (get_birthdate, get_birthplace_handle, get_deathdate,
                   get_deathplace_handle)


class PersonResourceHelper(GrampsObjectResourceHelper):
    """Person resource helper."""

    gramps_class_name = "Person"

    def object_denormalize(self, obj):  # pylint: disable=no-self-use
        """Denormalize person attributes if needed."""
        db = self.db
        obj.profile = {
            "birth_date": get_birthdate(db, obj),
            "birth_place": get_birthplace_handle(db, obj),
            "death_date": get_deathdate(db, obj),
            "death_place": get_deathplace_handle(db, obj),
            "name_given": name_displayer.display_given(obj),
            "name_surname": obj.primary_name.get_surname(),
            "parents_primary": obj.get_main_parents_family_handle(),
        }
        return obj


class PersonResource(GrampsObjectProtectedResource, PersonResourceHelper):
    """Person resource."""


class PeopleResource(GrampsObjectsProtectedResource, PersonResourceHelper):
    """People resource."""
