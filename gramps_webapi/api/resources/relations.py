#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Relation API Resource."""

from typing import Dict

from flask import Response, abort
from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.relationship import get_relationship_calculator
from webargs import fields, validate
from webargs.flaskparser import use_args

from ...types import Handle
from ..util import get_dbstate, get_locale_for_language
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .util import get_person_by_handle


class RelationResource(ProtectedResource, GrampsJSONEncoder):
    """Relation resource."""

    @use_args(
        {
            "depth": fields.Integer(missing=15),
            "locale": fields.Str(missing=None, validate=validate.Length(min=1, max=5)),
        },
        location="query",
    )
    def get(self, args: Dict, handle1: Handle, handle2: Handle) -> Response:
        """Get the most direct relationship between two people."""
        db_handle = get_dbstate().db
        person1 = get_person_by_handle(db_handle, handle1)
        if person1 == {}:
            abort(404)

        person2 = get_person_by_handle(db_handle, handle2)
        if person2 == {}:
            abort(404)

        locale = GRAMPS_LOCALE
        if args["locale"] is not None:
            locale = get_locale_for_language(args["locale"], default=True)

        calc = get_relationship_calculator(reinit=True, clocale=locale)
        calc.set_depth(args["depth"])

        data = calc.get_one_relationship(db_handle, person1, person2, extra_info=True)
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

    @use_args(
        {
            "depth": fields.Integer(missing=15),
            "locale": fields.Str(missing=None, validate=validate.Length(min=1, max=5)),
        },
        location="query",
    )
    def get(self, args: Dict, handle1: Handle, handle2: Handle) -> Response:
        """Get all possible relationships between two people."""
        db_handle = get_dbstate().db
        person1 = get_person_by_handle(db_handle, handle1)
        if person1 == {}:
            abort(404)

        person2 = get_person_by_handle(db_handle, handle2)
        if person2 == {}:
            abort(404)

        locale = GRAMPS_LOCALE
        if args["locale"] is not None:
            locale = get_locale_for_language(args["locale"], default=True)

        calc = get_relationship_calculator(reinit=True, clocale=locale)
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
