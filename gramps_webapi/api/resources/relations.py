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
from marshmallow import Schema
from webargs import fields, validate

from ...auth.const import PERM_VIEW_PRIVATE
from ..auth import has_permissions
from ...types import Handle
from ..cache import request_cache_decorator
from ..blueprint import api_blueprint
from ..util import (
    abort_with_message,
    get_db_handle,
    get_locale_for_language,
    get_tree_from_jwt_or_fail,
)
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .metadata import _get_dbid_from_tree_id
from .relationship_graph import get_relationship_graph
from .schemas import RelationshipItemSchema, RelationshipSchema


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
        db_handle = get_db_handle()
        # Existence checks go through the normal (possibly privacy-proxied)
        # db handle, same as before -- a private person 404s exactly as
        # today, unrelated to the fast path's own privacy filtering below.
        try:
            db_handle.get_person_from_handle(handle1)
        except HandleError:
            abort_with_message(404, f"Person {handle1} not found")
        try:
            db_handle.get_person_from_handle(handle2)
        except HandleError:
            abort_with_message(404, f"Person {handle2} not found")

        tree_id = get_tree_from_jwt_or_fail()
        dbid = _get_dbid_from_tree_id(tree_id)
        locale = get_locale_for_language(args["locale"], default=True)
        graph = get_relationship_graph(db_handle, dbid, locale=locale)
        restricted = not has_permissions({PERM_VIEW_PRIVATE})
        rel_str, dist_orig, dist_other = graph.relationship(
            handle1, handle2, restricted=restricted, depth=args["depth"]
        )
        return self.response(
            200,
            {
                "relationship_string": rel_str,
                "distance_common_origin": dist_orig,
                "distance_common_other": dist_other,
            },
        )


class RelationsResource(ProtectedResource, GrampsJSONEncoder):
    """Relations resource."""

    @api_blueprint.response(200, RelationshipItemSchema(many=True))
    @api_blueprint.arguments(RelationQueryArgs, location="query")
    @request_cache_decorator
    def get(self, args: Dict, handle1: Handle, handle2: Handle) -> Response:
        """Get all possible relationships between two people."""
        db_handle = get_db_handle()
        try:
            db_handle.get_person_from_handle(handle1)
        except HandleError:
            abort_with_message(404, f"Person {handle1} not found")
        try:
            db_handle.get_person_from_handle(handle2)
        except HandleError:
            abort_with_message(404, f"Person {handle2} not found")

        tree_id = get_tree_from_jwt_or_fail()
        dbid = _get_dbid_from_tree_id(tree_id)
        locale = get_locale_for_language(args["locale"], default=True)
        graph = get_relationship_graph(db_handle, dbid, locale=locale)
        restricted = not has_permissions({PERM_VIEW_PRIVATE})
        result = graph.all_relationships(
            handle1, handle2, restricted=restricted, depth=args["depth"]
        )
        return self.response(200, result)
