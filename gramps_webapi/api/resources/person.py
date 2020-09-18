"""Person API resource."""

from gramps.gen.display.name import displayer as name_displayer

from .base import GrampsObjectResource


class PersonResource(GrampsObjectResource):
    """Person resource."""

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
