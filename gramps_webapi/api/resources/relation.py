"""Relation API Resource."""

from flask import abort
from gramps.gen.db.base import DbReadBase
from gramps.gen.relationship import RelationshipCalculator
from webargs import fields
from webargs.flaskparser import use_args

from ..util import get_dbstate
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .util import get_person_by_handle


class RelationResource(ProtectedResource, GrampsJSONEncoder):
    """Relation resource."""

    @property
    def db(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    @use_args(
        {"depth": fields.Integer(), "all": fields.Boolean()},
        location="query",
    )
    def get(self, args, handle1: str, handle2: str):
        """Get the relationship between two people."""
        db = self.db
        person1 = get_person_by_handle(db, handle1)
        if person1 is None:
            abort(404)

        person2 = get_person_by_handle(db, handle2)
        if person2 is None:
            abort(404)

        calc = RelationshipCalculator()
        if "depth" in args:
            calc.set_depth(args["depth"])

        if "all" in args and args["all"]:
            data = calc.get_all_relationships(db, person1, person2)
            index = 0
            result = []
            while index < len(data[0]):
                result.append(
                    {
                        "relationship_string": data[0][index],
                        "common_ancestors": data[1][index],
                    }
                )
                index = index + 1
            return self.response(result)

        data = calc.get_one_relationship(db, person1, person2, extra_info=True)
        return self.response(
            {
                "relationship_string": data[0],
                "distance_common_origin": data[1],
                "distance_common_other": data[2],
            }
        )
