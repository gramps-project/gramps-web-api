"""Person API resource."""

from gramps.gen.display.name import displayer as name_displayer

from .base import (
    GrampsObjectHelper,
    GrampsObjectProtectedResource,
    GrampsObjectsProtectedResource,
)


class PersonResourceHelper(GrampsObjectHelper):
    """Person resource helper."""

    gramps_class_name = "Person"

    @staticmethod
    def object_to_dict(obj):  # pylint: disable=no-self-use
        """Return the person as a dictionary."""
        return {
            "gramps_id": obj.gramps_id,
            "name_given": name_displayer.display_given(obj),
            "name_surname": obj.primary_name.get_surname(),
            "gender": obj.gender,
        }


class PersonResource(GrampsObjectProtectedResource, PersonResourceHelper):
    """Person resource."""


class PeopleResource(GrampsObjectsProtectedResource, PersonResourceHelper):
    """People resource."""
