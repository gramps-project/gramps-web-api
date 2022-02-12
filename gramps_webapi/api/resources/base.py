#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Base for Gramps object API resources."""

import json
from abc import abstractmethod
from typing import Dict, List, Sequence

from flask import Response, abort, current_app, request
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db import DbTxn
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from gramps.gen.lib.serialize import from_json
from gramps.gen.utils.grampslocale import GrampsLocale
from webargs import fields, validate

from ...auth.const import PERM_ADD_OBJ, PERM_DEL_OBJ, PERM_EDIT_OBJ
from ..auth import require_permissions
from ..search import SearchIndexer
from ..util import get_db_handle, get_locale_for_language, use_args
from . import ProtectedResource, Resource
from .delete import delete_object
from .emit import GrampsJSONEncoder
from .filters import apply_filter
from .match import match_dates
from .sort import sort_objects
from .util import (
    add_object,
    fix_object_dict,
    get_backlinks,
    get_extended_attributes,
    get_missing_media_file_handles,
    get_reference_profile_for_object,
    get_soundex,
    hash_object,
    transaction_to_json,
    update_object,
    validate_object_dict,
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

    def match_dates(self, handles: List[str], date: str):
        """If supported filter objects using date mask."""
        if self.gramps_class_name in ["Event", "Media", "Citation"]:
            return match_dates(self.db_handle, self.gramps_class_name, handles, date)
        return handles

    @property
    def db_handle(self) -> DbReadBase:
        """Get the readonly database instance."""
        return get_db_handle(readonly=True)

    @property
    def db_handle_writable(self) -> DbReadBase:
        """Get the writable database instance."""
        return get_db_handle(readonly=False)

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

    def _parse_object(self) -> GrampsObject:
        """Parse the object."""
        obj_dict = request.json
        if obj_dict is None:
            abort(400)
        if "_class" not in obj_dict:
            obj_dict["_class"] = self.gramps_class_name
        elif obj_dict["_class"] != self.gramps_class_name:
            abort(400)
        try:
            obj_dict = fix_object_dict(obj_dict)
        except ValueError:
            abort(400)
        if not validate_object_dict(obj_dict):
            abort(400)
        return from_json(json.dumps(obj_dict))

    def has_handle(self, handle: str) -> bool:
        """Check if the handle exists in the database."""
        query_method = self.db_handle.method("has_%s_handle", self.gramps_class_name)
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
                        "ratings",
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
        get_etag = hash_object(obj)
        return self.response(
            200, self.full_object(obj, args, locale=locale), args, etag=get_etag
        )

    def delete(self, handle: str) -> Response:
        """Delete the object."""
        require_permissions([PERM_DEL_OBJ])
        try:
            obj = self.get_object_from_handle(handle)
        except HandleError:
            abort(404)
        get_etag = hash_object(obj)
        for etag in request.if_match:
            if etag != get_etag:
                abort(412)
        trans_dict = delete_object(
            self.db_handle_writable, handle, self.gramps_class_name
        )
        # update search index
        indexer: SearchIndexer = current_app.config["SEARCH_INDEXER"]
        with indexer.get_writer(overwrite=False, use_async=True) as writer:
            indexer.delete_object(writer, handle)
        return self.response(200, trans_dict, total_items=len(trans_dict))

    def put(self, handle: str) -> Response:
        """Modify an existing object."""
        require_permissions([PERM_EDIT_OBJ])
        try:
            obj_old = self.get_object_from_handle(handle)
        except HandleError:
            abort(404)
        get_etag = hash_object(obj_old)
        for etag in request.if_match:
            if etag != get_etag:
                abort(412)
        obj = self._parse_object()
        if not obj:
            abort(400)
        db_handle = self.db_handle_writable
        with DbTxn("Edit object", db_handle) as trans:
            try:
                update_object(db_handle, obj, trans)
            except ValueError:
                abort(400)
            trans_dict = transaction_to_json(trans)
        # update search index
        indexer: SearchIndexer = current_app.config["SEARCH_INDEXER"]
        with indexer.get_writer(overwrite=False, use_async=True) as writer:
            for _trans_dict in trans_dict:
                handle = _trans_dict["handle"]
                class_name = _trans_dict["_class"]
                indexer.add_or_update_object(writer, handle, db_handle, class_name)
        return self.response(200, trans_dict, total_items=len(trans_dict))


class GrampsObjectsResource(GrampsObjectResourceHelper, Resource):
    """Resource for multiple objects."""

    @use_args(
        {
            "backlinks": fields.Boolean(missing=False),
            "dates": fields.Str(
                missing=None,
                validate=validate.Regexp(
                    r"^([0-9]+|\*)/([1-9]|1[0-2]|\*)/([1-9]|1[0-9]|2[0-9]|3[0-1]|\*)$|"
                    r"^-[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])$|"
                    r"^[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])-$|"
                    r"^[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])-"
                    r"[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])$"
                ),
            ),
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
                        "ratings",
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
            "filemissing": fields.Boolean(missing=False),
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

        if self.gramps_class_name == "Media" and args.get("filemissing"):
            handles = get_missing_media_file_handles(self.db_handle, handles)

        if args["dates"]:
            handles = self.match_dates(handles, args["dates"])

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

    def post(self) -> Response:
        """Post a new object."""
        require_permissions([PERM_ADD_OBJ])
        obj = self._parse_object()
        if not obj:
            abort(400)
        db_handle = self.db_handle_writable
        with DbTxn("Add objects", db_handle) as trans:
            try:
                add_object(db_handle, obj, trans, fail_if_exists=True)
            except ValueError:
                abort(400)
            trans_dict = transaction_to_json(trans)
        # update search index
        indexer: SearchIndexer = current_app.config["SEARCH_INDEXER"]
        with indexer.get_writer(overwrite=False, use_async=True) as writer:
            for _trans_dict in trans_dict:
                handle = _trans_dict["handle"]
                class_name = _trans_dict["_class"]
                indexer.add_or_update_object(writer, handle, db_handle, class_name)
        return self.response(201, trans_dict, total_items=len(trans_dict))


class GrampsObjectProtectedResource(GrampsObjectResource, ProtectedResource):
    """Resource for a single object, requiring authentication."""


class GrampsObjectsProtectedResource(GrampsObjectsResource, ProtectedResource):
    """Resource for a multiple objects, requiring authentication."""
