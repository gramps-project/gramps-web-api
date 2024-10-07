#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2023      David Straub
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
from typing import Dict, List

import gramps_ql as gql
import object_ql as oql
from flask import Response, abort, request
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db import DbTxn
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from gramps.gen.lib.serialize import from_json
from gramps.gen.utils.grampslocale import GrampsLocale
from pyparsing.exceptions import ParseBaseException
from webargs import fields, validate

from ...auth.const import PERM_ADD_OBJ, PERM_DEL_OBJ, PERM_EDIT_OBJ
from ...const import GRAMPS_OBJECT_PLURAL
from ..auth import require_permissions
from ..search import SearchIndexer, get_search_indexer
from ..util import (
    check_quota_people,
    get_db_handle,
    get_locale_for_language,
    get_tree_from_jwt,
    update_usage_people,
    use_args,
)
from . import ProtectedResource, Resource
from .delete import delete_object
from .emit import GrampsJSONEncoder
from .filters import apply_filter
from .match import match_dates
from .sort import sort_objects
from .util import (
    abort_with_message,
    add_object,
    app_has_semantic_search,
    filter_missing_files,
    fix_object_dict,
    get_backlinks,
    get_extended_attributes,
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
                abort_with_message(
                    422, f"Option soundex is not allowed for {self.gramps_class_name}"
                )
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
        self, objects: List[GrampsObject], args: Dict, locale: GrampsLocale = glocale
    ) -> List:
        """Sort the list of objects as needed."""
        return sort_objects(
            self.db_handle, self.gramps_class_name, objects, args, locale=locale
        )

    def match_dates(self, objects: List[GrampsObject], date: str) -> List[GrampsObject]:
        """If supported filter objects using date mask."""
        if self.gramps_class_name in ["Event", "Media", "Citation"]:
            return match_dates(objects, date)
        return objects

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
            abort_with_message(400, "Empty object")
        if "_class" not in obj_dict:
            obj_dict["_class"] = self.gramps_class_name
        elif obj_dict["_class"] != self.gramps_class_name:
            abort_with_message(400, "Wrong object type")
        try:
            obj_dict = fix_object_dict(obj_dict)
        except ValueError as exc:
            abort_with_message(400, "Error while processing object")
        if not validate_object_dict(obj_dict):
            abort_with_message(400, "Schema validation failed")
        return from_json(json.dumps(obj_dict))

    def has_handle(self, handle: str) -> bool:
        """Check if the handle exists in the database."""
        query_method = self.db_handle.method("has_%s_handle", self.gramps_class_name)
        return query_method(handle)


class GrampsObjectResource(GrampsObjectResourceHelper, Resource):
    """Resource for a single object."""

    @use_args(
        {
            "backlinks": fields.Boolean(load_default=False),
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
            "locale": fields.Str(
                load_default=None, validate=validate.Length(min=1, max=5)
            ),
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
            "soundex": fields.Boolean(load_default=False),
            "strip": fields.Boolean(load_default=False),
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
                abort_with_message(412, "Resource does not match provided ETag")
        trans_dict = delete_object(
            self.db_handle_writable, handle, self.gramps_class_name
        )
        # update usage
        if self.gramps_class_name == "Person":
            update_usage_people()
        # update search index
        tree = get_tree_from_jwt()
        indexer: SearchIndexer = get_search_indexer(tree)
        indexer.delete_object(handle=handle, class_name=self.gramps_class_name)
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
                abort_with_message(412, "Resource does not match provided ETag")
        obj = self._parse_object()
        if not obj:
            abort_with_message(400, "Empty object")
        db_handle = self.db_handle_writable
        with DbTxn(f"Edit {self.gramps_class_name}", db_handle) as trans:
            try:
                update_object(db_handle, obj, trans)
            except ValueError as exc:
                abort_with_message(400, "Error while updating object")
            trans_dict = transaction_to_json(trans)
        # update search index
        tree = get_tree_from_jwt()
        indexer: SearchIndexer = get_search_indexer(tree)
        for _trans_dict in trans_dict:
            handle = _trans_dict["handle"]
            class_name = _trans_dict["_class"]
            indexer.add_or_update_object(handle, db_handle, class_name)
        if app_has_semantic_search():
            indexer: SearchIndexer = get_search_indexer(tree, semantic=True)
            for _trans_dict in trans_dict:
                handle = _trans_dict["handle"]
                class_name = _trans_dict["_class"]
                indexer.add_or_update_object(handle, db_handle, class_name)
        return self.response(200, trans_dict, total_items=len(trans_dict))


class GrampsObjectsResource(GrampsObjectResourceHelper, Resource):
    """Resource for multiple objects."""

    @use_args(
        {
            "backlinks": fields.Boolean(load_default=False),
            "dates": fields.Str(
                load_default=None,
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
            "gql": fields.Str(validate=validate.Length(min=1)),
            "oql": fields.Str(validate=validate.Length(min=1)),
            "gramps_id": fields.Str(validate=validate.Length(min=1)),
            "keys": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "locale": fields.Str(
                load_default=None, validate=validate.Length(min=1, max=5)
            ),
            "page": fields.Integer(load_default=0, validate=validate.Range(min=1)),
            "pagesize": fields.Integer(load_default=20, validate=validate.Range(min=1)),
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
            "soundex": fields.Boolean(load_default=False),
            "strip": fields.Boolean(load_default=False),
            "filemissing": fields.Boolean(load_default=False),
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

        # load all objects to memory
        objects_name = GRAMPS_OBJECT_PLURAL[self.gramps_class_name]
        iter_objects_method = self.db_handle.method("iter_%s", objects_name)
        objects = list(iter_objects_method())

        # for all objects except events, repos, and notes, Gramps supports
        # a database-backed default sort order. Use that if no sort order
        # requested.
        query_method = self.db_handle.method("get_%s_handles", self.gramps_class_name)
        if self.gramps_class_name in ["Event", "Repository", "Note"]:
            handles = query_method()
        else:
            handles = query_method(sort_handles=True, locale=locale)
        handle_index = {handle: index for index, handle in enumerate(handles)}
        # sort objects by the sorted handle order
        objects = sorted(
            objects, key=lambda obj: handle_index.get(obj.handle, len(handles) + 1)
        )

        if "filter" in args or "rules" in args:
            handles = [obj.handle for obj in objects]
            handles = apply_filter(
                self.db_handle, args, self.gramps_class_name, handles
            )
            objects = [obj for obj in objects if obj.handle in set(handles)]

        if "gql" in args:
            try:
                objects = [
                    obj
                    for obj in objects
                    if gql.match(query=args["gql"], obj=obj, db=self.db_handle)
                ]
            except (ParseBaseException, ValueError, TypeError) as e:
                abort_with_message(422, str(e))

        if "oql" in args:
            try:
                objects = [
                    obj
                    for obj in objects
                    if oql.match(query=args["oql"], obj=obj, db=self.db_handle)
                ]
            except (ParseBaseException, ValueError, TypeError) as e:
                abort_with_message(422, str(e))

        if self.gramps_class_name == "Media" and args.get("filemissing"):
            objects = filter_missing_files(objects)

        if args["dates"]:
            objects = self.match_dates(objects, args["dates"])

        if "sort" in args:
            objects = self.sort_objects(objects, args["sort"], locale=locale)

        total_items = len(objects)

        if args["page"] > 0:
            offset = (args["page"] - 1) * args["pagesize"]
            objects = objects[offset : offset + args["pagesize"]]

        return self.response(
            200,
            [self.full_object(obj, args, locale=locale) for obj in objects],
            args,
            total_items=total_items,
        )

    def post(self) -> Response:
        """Post a new object."""
        require_permissions([PERM_ADD_OBJ])
        # check quota
        if self.gramps_class_name == "Person":
            check_quota_people(to_add=1)
        obj = self._parse_object()
        if not obj:
            abort_with_message(400, "Empty object")
        db_handle = self.db_handle_writable
        with DbTxn(f"New {self.gramps_class_name}", db_handle) as trans:
            try:
                add_object(db_handle, obj, trans, fail_if_exists=True)
            except ValueError:
                abort_with_message(400, "Error while adding object")
            trans_dict = transaction_to_json(trans)
        # update usage
        if self.gramps_class_name == "Person":
            update_usage_people()
        # update search index
        tree = get_tree_from_jwt()
        indexer: SearchIndexer = get_search_indexer(tree)
        for _trans_dict in trans_dict:
            handle = _trans_dict["handle"]
            class_name = _trans_dict["_class"]
            indexer.add_or_update_object(handle, db_handle, class_name)
        if app_has_semantic_search():
            indexer: SearchIndexer = get_search_indexer(tree, semantic=True)
            for _trans_dict in trans_dict:
                handle = _trans_dict["handle"]
                class_name = _trans_dict["_class"]
                indexer.add_or_update_object(handle, db_handle, class_name)
        return self.response(201, trans_dict, total_items=len(trans_dict))


class GrampsObjectProtectedResource(GrampsObjectResource, ProtectedResource):
    """Resource for a single object, requiring authentication."""


class GrampsObjectsProtectedResource(GrampsObjectsResource, ProtectedResource):
    """Resource for a multiple objects, requiring authentication."""
