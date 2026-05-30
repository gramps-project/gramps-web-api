#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

"""Merge API resources for primary Gramps objects."""

import types
from typing import Type

from flask_jwt_extended import get_jwt_identity
from gramps.gen.errors import HandleError, MergeError
from gramps.gen.merge.mergecitationquery import MergeCitationQuery
from gramps.gen.merge.mergeeventquery import MergeEventQuery
from gramps.gen.merge.mergefamilyquery import MergeFamilyQuery
from gramps.gen.merge.mergemediaquery import MergeMediaQuery
from gramps.gen.merge.mergenotequery import MergeNoteQuery
from gramps.gen.merge.mergepersonquery import MergePersonQuery
from gramps.gen.merge.mergeplacequery import MergePlaceQuery
from gramps.gen.merge.mergerepositoryquery import MergeRepositoryQuery
from gramps.gen.merge.mergesourcequery import MergeSourceQuery
from marshmallow import Schema
from webargs import fields

from gramps_webapi.types import ResponseReturnValue

from ...auth.const import PERM_DEL_OBJ, PERM_EDIT_OBJ
from ..auth import require_permissions
from ..blueprint import api_blueprint
from ..search import SearchIndexer, get_search_indexer, get_semantic_search_indexer
from ..tasks import run_task, update_search_indices_from_transaction
from ..util import get_db_handle, get_tree_from_jwt_or_fail
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .util import abort_with_message, app_has_semantic_search


def _update_search_index(
    titanic_handle: str, phoenix_handle: str, class_name: str
) -> None:
    """Remove titanic from index and schedule re-indexing of phoenix."""
    tree = get_tree_from_jwt_or_fail()
    indexer: SearchIndexer = get_search_indexer(tree)
    indexer.delete_object(handle=titanic_handle, class_name=class_name)
    if app_has_semantic_search():
        get_semantic_search_indexer(tree).delete_object(
            handle=titanic_handle, class_name=class_name
        )
    run_task(
        update_search_indices_from_transaction,
        trans_dict=[{"handle": phoenix_handle, "_class": class_name}],
        tree=tree,
        user_id=get_jwt_identity(),
    )


class PersonMergeArgs(Schema):
    """Optional body arguments for person merge."""

    family_merger = fields.Boolean(
        load_default=True,
        metadata={
            "description": (
                "If true (default), merge duplicate spouse/parent families that "
                "result from merging the two persons."
            )
        },
    )


class FamilyMergeArgs(Schema):
    """Optional body arguments for family merge."""

    phoenix_father_handle = fields.Str(
        load_default=None,
        metadata={
            "description": (
                "Handle of the person to keep as father of the merged family. "
                "If omitted, the phoenix family's existing father is kept."
            )
        },
    )
    phoenix_mother_handle = fields.Str(
        load_default=None,
        metadata={
            "description": (
                "Handle of the person to keep as mother of the merged family. "
                "If omitted, the phoenix family's existing mother is kept."
            )
        },
    )


class MergePersonResource(GrampsJSONEncoder, ProtectedResource):
    """Merge two Person objects; phoenix survives, titanic is deleted."""

    @api_blueprint.response(200, Schema())
    @api_blueprint.arguments(PersonMergeArgs, location="json")
    def post(
        self, args: dict, phoenix_handle: str, titanic_handle: str
    ) -> ResponseReturnValue:
        """Merge two people. Phoenix survives; titanic is deleted."""
        require_permissions([PERM_EDIT_OBJ, PERM_DEL_OBJ])
        db = get_db_handle(readonly=False)
        try:
            phoenix = db.get_person_from_handle(phoenix_handle)
        except HandleError:
            abort_with_message(404, "Phoenix handle not found")
        try:
            titanic = db.get_person_from_handle(titanic_handle)
        except HandleError:
            abort_with_message(404, "Titanic handle not found")
        try:
            MergePersonQuery(db, phoenix, titanic).execute(
                family_merger=args["family_merger"]
            )
        except MergeError as exc:
            abort_with_message(409, str(exc))
        _update_search_index(titanic_handle, phoenix_handle, "Person")
        return self.response(200, {})


class MergeFamilyResource(GrampsJSONEncoder, ProtectedResource):
    """Merge two Family objects; phoenix survives, titanic is deleted."""

    @api_blueprint.response(200, Schema())
    @api_blueprint.arguments(FamilyMergeArgs, location="json")
    def post(
        self, args: dict, phoenix_handle: str, titanic_handle: str
    ) -> ResponseReturnValue:
        """Merge two families. Phoenix survives; titanic is deleted."""
        require_permissions([PERM_EDIT_OBJ, PERM_DEL_OBJ])
        db = get_db_handle(readonly=False)
        try:
            phoenix = db.get_family_from_handle(phoenix_handle)
        except HandleError:
            abort_with_message(404, "Phoenix handle not found")
        try:
            titanic = db.get_family_from_handle(titanic_handle)
        except HandleError:
            abort_with_message(404, "Titanic handle not found")
        try:
            MergeFamilyQuery(
                db,
                phoenix,
                titanic,
                phoenix_fh=args.get("phoenix_father_handle"),
                phoenix_mh=args.get("phoenix_mother_handle"),
            ).execute()
        except MergeError as exc:
            abort_with_message(409, str(exc))
        except AssertionError:
            abort_with_message(400, "Invalid parent handle")
        _update_search_index(titanic_handle, phoenix_handle, "Family")
        return self.response(200, {})


class _SimpleMergeResource(GrampsJSONEncoder, ProtectedResource):
    """Base for merge resources with no extra body arguments.

    Subclasses must set gramps_class_name and _merge_query_class.
    These query classes (Event, Place, Source, Citation, Repository, Media, Note)
    accept a dbstate-like object rather than a bare db handle, so we wrap the
    db handle in a SimpleNamespace with a .db attribute before passing it in.
    """

    gramps_class_name: str
    _merge_query_class: Type

    @api_blueprint.response(200, Schema())
    def post(self, phoenix_handle: str, titanic_handle: str) -> ResponseReturnValue:
        """Merge two objects. Phoenix survives; titanic is deleted."""
        require_permissions([PERM_EDIT_OBJ, PERM_DEL_OBJ])
        db = get_db_handle(readonly=False)
        get_method = db.method("get_%s_from_handle", self.gramps_class_name)
        try:
            phoenix = get_method(phoenix_handle)
        except HandleError:
            abort_with_message(404, "Phoenix handle not found")
        try:
            titanic = get_method(titanic_handle)
        except HandleError:
            abort_with_message(404, "Titanic handle not found")
        try:
            self._merge_query_class(
                types.SimpleNamespace(db=db), phoenix, titanic
            ).execute()
        except MergeError as exc:
            abort_with_message(409, str(exc))
        _update_search_index(titanic_handle, phoenix_handle, self.gramps_class_name)
        return self.response(200, {})


class MergeEventResource(_SimpleMergeResource):
    """Merge two Event objects."""

    gramps_class_name = "Event"
    _merge_query_class = MergeEventQuery


class MergePlaceResource(_SimpleMergeResource):
    """Merge two Place objects."""

    gramps_class_name = "Place"
    _merge_query_class = MergePlaceQuery


class MergeSourceResource(_SimpleMergeResource):
    """Merge two Source objects."""

    gramps_class_name = "Source"
    _merge_query_class = MergeSourceQuery


class MergeCitationResource(_SimpleMergeResource):
    """Merge two Citation objects."""

    gramps_class_name = "Citation"
    _merge_query_class = MergeCitationQuery


class MergeRepositoryResource(_SimpleMergeResource):
    """Merge two Repository objects."""

    gramps_class_name = "Repository"
    _merge_query_class = MergeRepositoryQuery


class MergeMediaResource(_SimpleMergeResource):
    """Merge two Media objects."""

    gramps_class_name = "Media"
    _merge_query_class = MergeMediaQuery


class MergeNoteResource(_SimpleMergeResource):
    """Merge two Note objects."""

    gramps_class_name = "Note"
    _merge_query_class = MergeNoteQuery
