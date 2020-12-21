#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Base for Gramps object API resources."""

from abc import abstractmethod
from typing import Dict, List

from flask import Response, abort
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from gramps.gen.utils.grampslocale import GrampsLocale
from webargs import fields, validate

from ..util import use_args
from ..util import get_db_handle, get_locale_for_language
from . import ProtectedResource, Resource
from .emit import GrampsJSONEncoder
from .filters import apply_filter
from .sort import sort_objects
from .util import (
    get_backlinks,
    get_reference_profile_for_object,
    get_extended_attributes,
    get_soundex,
)


class GrampsObjectResourceHelper(GrampsJSONEncoder):
    """Gramps object helper class."""

    @property  # type: ignore
    @abstractmethod
    def gramps_class_name(self):
        """To be set on child classes."""

    def full_object(
        self, obj: GrampsObject, args: Dict, locale: GrampsLocale = glocale
    ) -> GrampsObject:
        """Get the full object with extended attributes and backlinks."""
        if args.get("backlinks"):
            obj.backlinks = get_backlinks(self.db_handle, obj.handle)
        if args.get("soundex"):
            if self.gramps_class_name not in ["Person", "Family"]:
                abort(422)
            obj.soundex = get_soundex(self.db_handle, obj, self.gramps_class_name)
        obj = self.object_extend(obj, args, locale=locale)
        if args.get("profile") and (
            "all" in args["profile"] or "references" in args["profile"]
        ):
            if not hasattr(obj, "profile"):
                # create profile if doesn't exist
                obj.profile = {}
            obj.profile["references"] = get_reference_profile_for_object(
                self.db_handle, obj, locale=locale
            )
        return obj

    def object_extend(
        self, obj: GrampsObject, args: Dict, locale: GrampsLocale = glocale
    ) -> GrampsObject:
        """Extend the base object attributes as needed."""
        if "extend" in args:
            obj.extended = get_extended_attributes(self.db_handle, obj, args)
        return obj

    def sort_objects(
        self, objs: List[str], args: Dict, locale: GrampsLocale = glocale
    ) -> List:
        """Sort the list of objects as needed."""
        return sort_objects(
            self.db_handle, self.gramps_class_name, objs, args, locale=locale
        )

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_db_handle()

    def get_object_from_gramps_id(self, gramps_id: str) -> GrampsObject:
        """Get the object given a Gramps ID."""
        query_method = self.db_handle.method(
            "get_%s_from_gramps_id", self.gramps_class_name
        )
        return query_method(gramps_id)

    def get_object_from_handle(self, handle: str) -> GrampsObject:
        """Get the object given a Gramps handle."""
        query_method = self.db_handle.method(
            "get_%s_from_handle", self.gramps_class_name
        )
        return query_method(handle)


class GrampsObjectResource(GrampsObjectResourceHelper, Resource):
    """Resource for a single object."""

    @use_args(
        {
            "backlinks": fields.Boolean(missing=False),
            "extend": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(
                    choices=[
                        "all",
                        "citation_list",
                        "event_ref_list",
                        "family_list",
                        "note_list",
                        "parent_family_list",
                        "person_ref_list",
                        "primary_parent_family",
                        "place",
                        "source_handle",
                        "father_handle",
                        "mother_handle",
                        "media_list",
                        "reporef_list",
                        "tag_list",
                        "backlinks",
                        "child_ref_list",
                    ]
                ),
            ),
            "formats": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "format_options": fields.Str(validate=validate.Length(min=1)),
            "keys": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "locale": fields.Str(missing=None, validate=validate.Length(min=1, max=5)),
            "profile": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(
                    choices=[
                        "all",
                        "self",
                        "families",
                        "events",
                        "age",
                        "span",
                        "references",
                    ]
                ),
            ),
            "skipkeys": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "soundex": fields.Boolean(missing=False),
            "strip": fields.Boolean(missing=False),
        },
        location="query",
    )
    def get(self, args: Dict, handle: str) -> Response:
        """Get the object."""
        try:
            obj = self.get_object_from_handle(handle)
        except HandleError:
            abort(404)
        locale = get_locale_for_language(args["locale"], default=True)
        return self.response(200, self.full_object(obj, args, locale=locale), args)


class GrampsObjectsResource(GrampsObjectResourceHelper, Resource):
    """Resource for multiple objects."""

    @use_args(
        {
            "backlinks": fields.Boolean(missing=False),
            "extend": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(
                    choices=[
                        "all",
                        "citation_list",
                        "event_ref_list",
                        "family_list",
                        "note_list",
                        "parent_family_list",
                        "person_ref_list",
                        "primary_parent_family",
                        "place",
                        "source_handle",
                        "father_handle",
                        "mother_handle",
                        "media_list",
                        "reporef_list",
                        "tag_list",
                        "backlinks",
                        "child_ref_list",
                    ]
                ),
            ),
            "filter": fields.Str(validate=validate.Length(min=1)),
            "formats": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "format_options": fields.Str(validate=validate.Length(min=1)),
            "gramps_id": fields.Str(validate=validate.Length(min=1)),
            "keys": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "locale": fields.Str(missing=None, validate=validate.Length(min=1, max=5)),
            "page": fields.Integer(missing=0, validate=validate.Range(min=1)),
            "pagesize": fields.Integer(missing=20, validate=validate.Range(min=1)),
            "profile": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(
                    choices=[
                        "all",
                        "self",
                        "families",
                        "events",
                        "age",
                        "span",
                        "references",
                    ]
                ),
            ),
            "rules": fields.Str(validate=validate.Length(min=1)),
            "skipkeys": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "sort": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "soundex": fields.Boolean(missing=False),
            "strip": fields.Boolean(missing=False),
        },
        location="query",
    )
    def get(self, args: Dict) -> Response:
        """Get all objects."""
        locale = get_locale_for_language(args["locale"], default=True)
        if "gramps_id" in args:
            obj = self.get_object_from_gramps_id(args["gramps_id"])
            if obj is None:
                abort(404)
            return self.response(
                200, [self.full_object(obj, args, locale=locale)], args, total_items=1
            )

        query_method = self.db_handle.method("get_%s_handles", self.gramps_class_name)
        if self.gramps_class_name in ["Event", "Repository", "Note"]:
            handles = query_method()
        else:
            handles = query_method(sort_handles=True, locale=locale)

        if "filter" in args or "rules" in args:
            handles = apply_filter(
                self.db_handle, args, self.gramps_class_name, handles
            )

        if "sort" in args:
            handles = self.sort_objects(handles, args["sort"], locale=locale)

        total_items = len(handles)

        if args["page"] > 0:
            offset = (args["page"] - 1) * args["pagesize"]
            handles = handles[offset : offset + args["pagesize"]]

        query_method = self.db_handle.method(
            "get_%s_from_handle", self.gramps_class_name
        )
        return self.response(
            200,
            [
                self.full_object(query_method(handle), args, locale=locale)
                for handle in handles
            ],
            args,
            total_items=total_items,
        )


class GrampsObjectProtectedResource(GrampsObjectResource, ProtectedResource):
    """Resource for a single object, requiring authentication."""


class GrampsObjectsProtectedResource(GrampsObjectsResource, ProtectedResource):
    """Resource for a multiple objects, requiring authentication."""
