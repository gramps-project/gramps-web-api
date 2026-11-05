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
from gramps.gen.db import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib import Person
from gramps.gen.relationship import get_relationship_calculator
from gramps.gen.types import PersonHandle
from marshmallow import Schema
from webargs import fields, validate

from gramps_webapi.api.people_families_cache import CachePeopleFamiliesProxy
from gramps_webapi.future_gramps.relationship_path import (
    find_connections,
    label_path,
)

from ...types import Handle
from ..cache import request_cache_decorator
from ..family_link_cache import get_family_link_graph
from ..blueprint import api_blueprint
from ..util import abort_with_message, get_db_handle, get_locale_for_language
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .schemas import (
    RelationshipItemSchema,
    RelationshipPathSchema,
    RelationshipSchema,
)
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


class RelationPathsQueryArgs(Schema):
    """Query arguments for the relation paths endpoint."""

    depth = fields.Integer(
        load_default=10,
        validate=validate.Range(min=1, max=30),
        metadata={
            "description": "Maximum number of links in a path (default 10, at most 30)."
        },
    )
    max = fields.Integer(
        load_default=5,
        validate=validate.Range(min=1, max=50),
        metadata={
            "description": "Maximum number of paths to return (default 5, at most 50)."
        },
    )
    blood_only = fields.Boolean(
        load_default=False,
        metadata={
            "description": "Only return paths that go up to a common ancestor and down again (default false)."
        },
    )
    locale = fields.Str(
        load_default=None,
        validate=validate.Length(min=1, max=5),
        metadata={
            "description": "Language code of the locale to use where applicable. Must be a valid code from the available translations."
        },
    )


def _get_person_or_404(db_handle: DbReadBase, handle: Handle) -> Person:
    """Get a person, aborting with 404 if missing or hidden by the private proxy."""
    try:
        person = db_handle.get_person_from_handle(handle)
    except HandleError:
        person = None
    if person is None:
        abort_with_message(404, f"Person {handle} not found")
        raise AssertionError  # for type checker
    return person


class RelationResource(ProtectedResource, GrampsJSONEncoder):
    """Relation resource."""

    @api_blueprint.response(200, RelationshipSchema())
    @api_blueprint.arguments(RelationQueryArgs, location="query")
    @request_cache_decorator
    def get(self, args: Dict, handle1: Handle, handle2: Handle) -> Response:
        """Get the most direct relationship between two people."""
        db_handle = CachePeopleFamiliesProxy(get_db_handle())
        person1 = _get_person_or_404(db_handle, handle1)
        person2 = _get_person_or_404(db_handle, handle2)

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
        person1 = _get_person_or_404(db_handle, handle1)
        person2 = _get_person_or_404(db_handle, handle2)

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


class RelationPathsResource(ProtectedResource, GrampsJSONEncoder):
    """Relation paths resource."""

    @api_blueprint.response(200, RelationshipPathSchema(many=True))
    @api_blueprint.arguments(RelationPathsQueryArgs, location="query")
    @request_cache_decorator
    def get(self, args: Dict, handle1: Handle, handle2: Handle) -> Response:
        """Get the chains of family links between two people, shortest first.

        Each step of a path is a person, how they are linked to the person
        before them, and their relationship to the first person, which is
        null when it has no name, for example through two marriages.
        """
        db_handle = get_db_handle()
        _get_person_or_404(db_handle, handle1)
        _get_person_or_404(db_handle, handle2)

        graph = get_family_link_graph(db_handle)
        paths = find_connections(
            graph,
            PersonHandle(handle1),
            PersonHandle(handle2),
            max_depth=args["depth"],
            max_results=args["max"],
            blood_only=args["blood_only"],
        )
        locale = get_locale_for_language(args["locale"], default=True)
        calc = get_relationship_calculator(reinit=True, clocale=locale)
        result = []
        for path in paths:
            labels = label_path(calc, db_handle, graph, path)
            result.append(
                {
                    "steps": [
                        {
                            "handle": handle,
                            "link": None if link is None else link.value,
                            "relationship_string": label,
                        }
                        for (handle, link), label in zip(path, labels)
                    ]
                }
            )
        return self.response(200, result)
