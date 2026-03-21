#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
# Copyright (C) 2025      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Relation API Resource."""

from typing import Dict

from flask import Response
from gramps.gen.errors import HandleError
from gramps.gen.relationship import get_relationship_calculator
from marshmallow import Schema
from webargs import fields, validate

from gramps_webapi.api.people_families_cache import CachePeopleFamiliesProxy

from ...types import Handle
from ..cache import request_cache_decorator
from ..blueprint import api_blueprint
from ..util import abort_with_message, get_db_handle, get_locale_for_language
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .schemas import RelationshipItemSchema, RelationshipSchema
from .util import get_one_relationship


class RelationQueryArgs(Schema):
    """Query arguments for relation endpoints."""

    depth = fields.Integer(
        load_default=15,
        validate=validate.Range(min=2),
        metadata={
            "description": "Maximum number of generations to search for a common ancestor (default 15)."
        },
    )
    locale = fields.Str(
        load_default=None,
        validate=validate.Length(min=1, max=5),
        metadata={
            "description": "Language code of the locale to use where applicable. Must be a valid code from the available translations."
        },
    )


class RelationResource(ProtectedResource, GrampsJSONEncoder):
    """Relation resource."""

    @api_blueprint.response(200, RelationshipSchema())
    @api_blueprint.arguments(RelationQueryArgs, location="query")
    @request_cache_decorator
    def get(self, args: Dict, handle1: Handle, handle2: Handle) -> Response:
        """Get the most direct relationship between two people."""
        db_handle = CachePeopleFamiliesProxy(get_db_handle())
        try:
            person1 = db_handle.get_person_from_handle(handle1)
        except HandleError:
            abort_with_message(404, f"Person {handle1} not found")
        try:
            person2 = db_handle.get_person_from_handle(handle2)
        except HandleError:
            abort_with_message(404, f"Person {handle2} not found")

        db_handle.cache_people()
        db_handle.cache_families()

        locale = get_locale_for_language(args["locale"], default=True)
        data = get_one_relationship(
            db_handle=db_handle,
            person1=person1,
            person2=person2,
            depth=args["depth"],
            locale=locale,
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

    @api_blueprint.response(200, RelationshipItemSchema(many=True))
    @api_blueprint.arguments(RelationQueryArgs, location="query")
    @request_cache_decorator
    def get(self, args: Dict, handle1: Handle, handle2: Handle) -> Response:
        """Get all possible relationships between two people."""
        db_handle = CachePeopleFamiliesProxy(get_db_handle())

        try:
            person1 = db_handle.get_person_from_handle(handle1)
        except HandleError:
            abort_with_message(404, f"Person {handle1} not found")

        try:
            person2 = db_handle.get_person_from_handle(handle2)
        except HandleError:
            abort_with_message(404, f"Person {handle2} not found")

        db_handle.cache_people()
        db_handle.cache_families()

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
