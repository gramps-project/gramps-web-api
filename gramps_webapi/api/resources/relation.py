"""Relation API Resource."""

from typing import Dict

from flask import Response, abort
from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.db.base import DbReadBase
from gramps.gen.relationship import RelationshipCalculator
from webargs import fields
from webargs.flaskparser import use_args

from ...types import Handle
from ..util import get_dbstate
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .util import get_person_by_handle


class RelationResource(ProtectedResource, GrampsJSONEncoder):
    """Relation resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    @use_args(
        {"depth": fields.Integer(), "locale": fields.Boolean(missing=False)},
        location="query",
    )
    def get(self, args: Dict, handle1: Handle, handle2: Handle) -> Response:
        """Get the most direct relationship between two people."""
        db_handle = self.db_handle
        person1 = get_person_by_handle(db_handle, handle1)
        if person1 == {}:
            abort(404)

        person2 = get_person_by_handle(db_handle, handle2)
        if person2 == {}:
            abort(404)

        calc = RelationshipCalculator()
        if "depth" in args:
            calc.set_depth(args["depth"])

        if args["locale"]:
            data = calc.get_one_relationship(
                db_handle, person1, person2, extra_info=True, olocale=GRAMPS_LOCALE
            )
        else:
            data = calc.get_one_relationship(
                db_handle, person1, person2, extra_info=True
            )
        return self.response(
            200,
            {
                "relationship_string": data[0],
                "distance_common_origin": data[1],
                "distance_common_other": data[2],
            },
        )


class RelationsResource(ProtectedResource, GrampsJSONEncoder):
    """Relations resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    @use_args(
        {
            "depth": fields.Integer(),
        },
        location="query",
    )
    def get(self, args: Dict, handle1: Handle, handle2: Handle) -> Response:
        """Get all possible relationships between two people."""
        db_handle = self.db_handle
        person1 = get_person_by_handle(db_handle, handle1)
        if person1 == {}:
            abort(404)

        person2 = get_person_by_handle(db_handle, handle2)
        if person2 == {}:
            abort(404)

        calc = RelationshipCalculator()
        if "depth" in args:
            calc.set_depth(args["depth"])

        data = calc.get_all_relationships(db_handle, person1, person2)
        result = []
        index = 0
        while index < len(data[0]):
            result.append(
                {
                    "relationship_string": data[0][index],
                    "common_ancestors": data[1][index],
                }
            )
            index = index + 1
        if result == []:
            result = [{}]
        return self.response(200, result)
