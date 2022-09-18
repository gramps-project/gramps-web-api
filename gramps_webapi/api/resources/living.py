#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
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

"""Living Calculator API Resource."""

from typing import Dict

from flask import Response, abort
from gramps.gen.utils.alive import probably_alive, probably_alive_range
from webargs import fields, validate

from ...types import Handle
from ..util import get_db_handle, get_locale_for_language, use_args
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .util import get_person_by_handle


class LivingResource(ProtectedResource, GrampsJSONEncoder):
    """Living calculator resource."""

    @use_args(
        {
            "average_generation_gap": fields.Integer(
                load_default=None, validate=validate.Range(min=1)
            ),
            "max_age_probably_alive": fields.Integer(
                load_default=None, validate=validate.Range(min=1)
            ),
            "max_sibling_age_difference": fields.Integer(
                load_default=None, validate=validate.Range(min=1)
            ),
        },
        location="query",
    )
    def get(self, args: Dict, handle: Handle) -> Response:
        """Determine if person alive."""
        db_handle = get_db_handle()
        person = get_person_by_handle(db_handle, handle)
        if person == {}:
            abort(404)

        data = probably_alive(
            person,
            db_handle,
            max_sib_age_diff=args["max_sibling_age_difference"],
            max_age_prob_alive=args["max_age_probably_alive"],
            avg_generation_gap=args["average_generation_gap"],
        )
        return self.response(200, {"living": data})


class LivingDatesResource(ProtectedResource, GrampsJSONEncoder):
    """Living calculator dates resource."""

    @use_args(
        {
            "average_generation_gap": fields.Integer(
                load_default=None, validate=validate.Range(min=1)
            ),
            "locale": fields.Str(
                load_default=None, validate=validate.Length(min=1, max=5)
            ),
            "max_age_probably_alive": fields.Integer(
                load_default=None, validate=validate.Range(min=1)
            ),
            "max_sibling_age_difference": fields.Integer(
                load_default=None, validate=validate.Range(min=1)
            ),
        },
        location="query",
    )
    def get(self, args: Dict, handle: Handle) -> Response:
        """Determine estimated birth and death dates."""
        db_handle = get_db_handle()
        locale = get_locale_for_language(args["locale"], default=True)
        person = get_person_by_handle(db_handle, handle)
        if person == {}:
            abort(404)

        data = probably_alive_range(
            person,
            db_handle,
            max_sib_age_diff=args["max_sibling_age_difference"],
            max_age_prob_alive=args["max_age_probably_alive"],
            avg_generation_gap=args["average_generation_gap"],
        )

        profile = {
            "birth": locale.date_displayer.display(data[0]),
            "death": locale.date_displayer.display(data[1]),
            "explain": data[2],
            "other": data[3],
        }
        return self.response(200, profile)
