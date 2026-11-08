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

"""Apply the same simple edits to many objects of one type."""

from typing import Any, Callable, Dict, List, Optional

from gramps.gen.db import DbTxn, DbWriteBase
from gramps.gen.errors import HandleError

from ...const import GRAMPS_OBJECT_PLURAL
from .util import transaction_to_json

OP_ADD_TAG = "add_tag"
OP_REMOVE_TAG = "remove_tag"
OP_SET_PRIVATE = "set_private"

TAG_OPS = (OP_ADD_TAG, OP_REMOVE_TAG)
EDIT_OPS = (*TAG_OPS, OP_SET_PRIVATE)

# Tags have neither tags nor privacy.
EDITABLE_NAMESPACES = [
    plural for name, plural in GRAMPS_OBJECT_PLURAL.items() if name != "Tag"
]

_NAMESPACE_TO_CLASS_NAME = {
    plural: name for name, plural in GRAMPS_OBJECT_PLURAL.items()
}


def _add_tag(obj, operation: Dict[str, Any]) -> bool:
    tag_handle = operation["handle"]
    if tag_handle in obj.get_tag_list():
        return False
    obj.add_tag(tag_handle)
    return True


def _remove_tag(obj, operation: Dict[str, Any]) -> bool:
    tag_handle = operation["handle"]
    if tag_handle not in obj.get_tag_list():
        return False
    obj.remove_tag(tag_handle)
    return True


def _set_private(obj, operation: Dict[str, Any]) -> bool:
    """Set the privacy of the primary object only, not of its secondary objects."""
    value = operation["value"]
    if obj.get_privacy() == value:
        return False
    obj.set_privacy(value)
    return True


_OP_METHODS: Dict[str, Callable[[Any, Dict[str, Any]], bool]] = {
    OP_ADD_TAG: _add_tag,
    OP_REMOVE_TAG: _remove_tag,
    OP_SET_PRIVATE: _set_private,
}


def validate_edit_operations(
    db_handle: DbWriteBase, operations: List[Dict[str, Any]]
) -> None:
    """Raise ValueError if an operation refers to a tag that does not exist."""
    for operation in operations:
        if operation["op"] in TAG_OPS and not db_handle.has_tag_handle(
            operation["handle"]
        ):
            raise ValueError(f"Tag {operation['handle']} does not exist")


def edit_objects_by_handle(
    db_handle: DbWriteBase,
    namespace: str,
    handles: List[str],
    operations: List[Dict[str, Any]],
    progress_cb: Optional[Callable] = None,
) -> List[Dict[str, Any]]:
    """Apply the operations to specific objects of a single type.

    All objects are edited in one transaction. Only objects that changed are
    committed, so the returned transaction lists real changes only. Handles of
    objects that do not exist are skipped.
    """
    if namespace not in EDITABLE_NAMESPACES:
        raise ValueError(f"Unknown namespace {namespace}")
    class_name = _NAMESPACE_TO_CLASS_NAME[namespace]
    validate_edit_operations(db_handle, operations)
    get_method = db_handle.method("get_%s_from_handle", class_name)
    commit_method = db_handle.method("commit_%s", class_name)
    with DbTxn(f"Edit {namespace}", db_handle) as trans:
        for i, handle in enumerate(handles):
            if progress_cb:
                progress_cb(current=i, total=len(handles))
            try:
                obj = get_method(handle)
            except HandleError:
                continue
            changed = False
            for operation in operations:
                changed |= _OP_METHODS[operation["op"]](obj, operation)
            if changed:
                commit_method(obj, trans)
        trans_dict = transaction_to_json(trans)
    return trans_dict
