#
# Gramps - a GTK+/GNOME based genealogy program
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

"""Facts API resource."""

from typing import Dict, Union

import gramps.gen.filters as filters
from flask import Response, abort
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.filters import GenericFilter
from gramps.gen.proxy import LivingProxyDb, PrivateProxyDb
from gramps.gen.user import User
from gramps.plugins.lib.librecords import find_records
from webargs import fields, validate

from ..util import abort_with_message, get_db_handle, get_locale_for_language, use_args
from . import ProtectedResource
from .emit import GrampsJSONEncoder

_ = glocale.translation.gettext

LIVING_FILTERS = {
    "IncludeAll": LivingProxyDb.MODE_INCLUDE_ALL,
    "FullNameOnly": LivingProxyDb.MODE_INCLUDE_FULL_NAME_ONLY,
    "LastNameOnly": LivingProxyDb.MODE_INCLUDE_LAST_NAME_ONLY,
    "ReplaceCompleteName": LivingProxyDb.MODE_REPLACE_COMPLETE_NAME,
    "ExcludeAll": LivingProxyDb.MODE_EXCLUDE_ALL,
}


def get_person_filter(db_handle: DbReadBase, args: Dict) -> Union[GenericFilter, None]:
    """Return the specified person filter."""
    if args["person"] is None:
        if args["gramps_id"] is not None or args["handle"] is not None:
            abort(422)
        return None

    if args["gramps_id"]:
        gramps_id = args["gramps_id"]
        if db_handle.get_person_from_gramps_id(gramps_id) is None:
            abort_with_message(422, "Person with this Gramps ID not found")
    else:
        try:
            person = db_handle.get_person_from_handle(args["handle"])
        except HandleError:
            abort_with_message(422, "Person with this handle not found")
        gramps_id = person.gramps_id

    person_filter = filters.GenericFilter()
    if args["person"] == "Descendants":
        person_filter.set_name(_("Descendants of %s") % gramps_id)
        person_filter.add_rule(filters.rules.person.IsDescendantOf([gramps_id, 1]))
    elif args["person"] == "DescendantFamilies":
        person_filter.set_name(_("Descendant Families of %s") % gramps_id)
        person_filter.add_rule(
            filters.rules.person.IsDescendantFamilyOf([gramps_id, 1])
        )
    elif args["person"] == "Ancestors":
        person_filter.set_name(_("Ancestors of %s") % gramps_id)
        person_filter.add_rule(filters.rules.person.IsAncestorOf([gramps_id, 1]))
    elif args["person"] == "CommonAncestor":
        person_filter.set_name(_("People with common ancestor with %s") % gramps_id)
        person_filter.add_rule(filters.rules.person.HasCommonAncestorWith([gramps_id]))
    else:
        person_filter = None
        filters.reload_custom_filters()
        for filter_class in filters.CustomFilters.get_filters("Person"):
            if args["person"] == filter_class.get_name():
                person_filter = filter_class
                break
    if person_filter is None:
        abort(422)
    return person_filter


class FactsResource(ProtectedResource, GrampsJSONEncoder):
    """Facts resource."""

    @use_args(
        {
            "gramps_id": fields.Str(load_default=None, validate=validate.Length(min=1)),
            "handle": fields.Str(load_default=None, validate=validate.Length(min=1)),
            "living": fields.Str(
                load_default="IncludeAll",
                validate=validate.OneOf(
                    [
                        "IncludeAll",
                        "FullNameOnly",
                        "LastNameOnly",
                        "ReplaceCompleteName",
                        "ExcludeAll",
                    ]
                ),
            ),
            "locale": fields.Str(
                load_default=None, validate=validate.Length(min=2, max=5)
            ),
            "person": fields.Str(load_default=None, validate=validate.Length(min=1)),
            "private": fields.Boolean(load_default=False),
            "rank": fields.Integer(load_default=1, validate=validate.Range(min=1)),
        },
        location="query",
    )
    def get(self, args: Dict) -> Response:
        """Get statistics from records."""
        db_handle = get_db_handle()
        locale = get_locale_for_language(args["locale"], default=True)
        person_filter = get_person_filter(db_handle, args)

        database = db_handle
        if args["private"]:
            database = PrivateProxyDb(db_handle)

        if args["living"] != "IncludeAll":
            database = LivingProxyDb(
                database,
                LIVING_FILTERS[args["living"]],
                llocale=locale,
            )

        records = find_records(
            database,
            person_filter,
            args["rank"],
            None,
            trans_text=locale.translation.sgettext,
            name_format=None,
            living_mode=LIVING_FILTERS["IncludeAll"],
            user=User(),
        )

        profiles = []
        for record in records:
            profile = {"description": record[0], "key": record[1], "objects": []}
            for item in record[2]:
                try:
                    value = item[1].format(precision=3, as_age=True, dlocale=locale)
                except AttributeError:
                    value = str(item[1])
                query_method = db_handle.method("get_%s_from_handle", item[3])
                obj = query_method(item[4])
                profile["objects"].append(
                    {
                        "gramps_id": obj.gramps_id,
                        "handle": item[4],
                        "name": str(item[2]),
                        "object": item[3],
                        "value": value,
                    }
                )
            profiles.append(profile)

        return self.response(200, profiles)
