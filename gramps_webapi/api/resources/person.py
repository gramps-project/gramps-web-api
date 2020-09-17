"""Person API resource."""

from flask_restful import Resource, abort
from gramps.gen.display.name import displayer as name_displayer

from ..util import get_dbstate


class Person(Resource):
    """Person resource."""

    def get(self, gramps_id: str):  # pylint: disable=no-self-use
        """Get."""
        dbstate = get_dbstate()
        person = dbstate.db.get_person_from_gramps_id(gramps_id)
        if person is None:
            return abort(404)
        return {
            "gramps_id": person.gramps_id,
            "name_given": name_displayer.display_given(person),
            "name_surname": person.primary_name.get_surname(),
            "gender": person.gender,
        }
