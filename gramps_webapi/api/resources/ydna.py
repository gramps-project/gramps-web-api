#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025  David Straub
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

"""Y-DNA resources."""

from __future__ import annotations
from dataclasses import asdict

import yclade
from gramps.gen.errors import HandleError
from gramps.gen.lib import Person
from webargs import fields, validate

from ..cache import request_cache_decorator
from ..util import get_db_handle, use_args, abort_with_message
from . import ProtectedResource


class PersonYDnaResource(ProtectedResource):
    """Resource for getting Y-DNA data for a person."""

    @use_args(
        {
            "locale": fields.Str(
                load_default=None, validate=validate.Length(min=2, max=5)
            ),
            "raw": fields.Bool(load_default=False),
        },
        location="query",
    )
    @request_cache_decorator
    def get(self, args: dict, handle: str):
        """Get Y-DNA data.

        The raw data is expected to be in a person attribute of type 'Y-DNA'
        in a format the yclade library understands.
        """
        db_handle = get_db_handle()
        try:
            person: Person | None = db_handle.get_person_from_handle(handle)
        except HandleError:
            abort_with_message(404, "Person not found")
        if person is None:
            abort_with_message(404, "Person not found")
            raise AssertionError  # for type checker
        attribute = next(
            (attr for attr in person.attribute_list if attr.type == "Y-DNA"), None
        )
        if attribute is None:
            return {}
        snp_string = attribute.value
        snp_results = yclade.snps.parse_snp_results(snp_string)
        tree_data = yclade.tree.get_yfull_tree_data()
        snp_results = yclade.snps.normalize_snp_results(
            snp_results=snp_results,
            snp_aliases=tree_data.snp_aliases,
        )
        ordered_clade_details = yclade.find.get_ordered_clade_details(
            tree=tree_data, snps=snp_results
        )
        if len(ordered_clade_details) == 0:
            return {}
        most_likely_clade = ordered_clade_details[0].name
        clade_lineage = yclade.find.get_clade_lineage(
            tree=tree_data, node=most_likely_clade
        )
        result = {
            "clade_lineage": [asdict(clade_info) for clade_info in clade_lineage],
            "tree_version": tree_data.version,
        }
        if args["raw"]:
            result["raw_data"] = snp_string
        return result
