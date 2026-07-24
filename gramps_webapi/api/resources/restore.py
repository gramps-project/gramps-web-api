#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025       David Straub
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

"""Restore a tree to the state of an uploaded backup ("reset to backup").

This computes the one-directional delta needed to make the live tree identical
to a backup file and applies it as add/update/delete operations, rather than
wiping the tree and re-importing. The diff itself is delegated to Gramps core
(``diff_dbs``); this module only projects its result onto reset actions and
applies them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from gramps.gen.config import config
from gramps.gen.db import DbTxn, DbWriteBase
from gramps.gen.db.base import DbReadBase
from gramps.gen.db.utils import make_database
from gramps.gen.merge.diff import diff_dbs
from gramps.gen.user import User

from ...const import GRAMPS_OBJECT_PLURAL
from .util import run_import


@dataclass
class ResetChangeset:
    """The changeset that makes a live tree identical to a backup snapshot.

    ``to_add`` and ``to_update`` hold the *backup* version of each object (to be
    committed into the live tree); ``to_delete`` holds ``(class_name, handle)``
    of live objects absent from the backup.
    """

    to_add: list[tuple[str, object]] = field(default_factory=list)
    to_update: list[tuple[str, object]] = field(default_factory=list)
    to_delete: list[tuple[str, str]] = field(default_factory=list)


def load_backup_db(file_name: str, extension: str) -> DbReadBase:
    """Import a backup file into an in-memory database and return the handle.

    The caller is responsible for closing the returned database. This mirrors
    ``dry_run_import`` but keeps the database open so it can be diffed against
    the live tree.
    """
    db_handle = make_database("sqlite")
    db_handle.load(":memory:")
    db_handle.set_feature("skip-import-additions", True)
    db_handle.set_prefixes(
        config.get("preferences.iprefix"),
        config.get("preferences.oprefix"),
        config.get("preferences.fprefix"),
        config.get("preferences.sprefix"),
        config.get("preferences.cprefix"),
        config.get("preferences.pprefix"),
        config.get("preferences.eprefix"),
        config.get("preferences.rprefix"),
        config.get("preferences.nprefix"),
    )
    try:
        run_import(
            db_handle=db_handle, file_name=file_name, extension=extension, delete=False
        )
    except Exception:
        # Never leak the in-memory database if the import fails.
        db_handle.close()
        raise
    return db_handle


def compute_reset_changeset(
    db_handle: DbReadBase, backup_db: DbReadBase
) -> ResetChangeset:
    """Compute the changeset to reset ``db_handle`` to the state of ``backup_db``.

    ``diff_dbs(live, backup)`` returns objects that differ (present in both),
    objects missing from the live tree (present only in the backup), and objects
    missing from the backup (present only in the live tree). For a reset these
    map directly onto update / add / delete.
    """
    diffs, missing_from_old, missing_from_new = diff_dbs(db_handle, backup_db, User())
    changeset = ResetChangeset()
    # objects in both but with differing content -> overwrite with backup version
    for class_name, _live_obj, backup_obj in diffs:
        changeset.to_update.append((class_name, backup_obj))
    # objects only in the backup -> add the backup version
    for class_name, backup_obj in missing_from_old:
        changeset.to_add.append((class_name, backup_obj))
    # objects only in the live tree -> delete
    for class_name, live_obj in missing_from_new:
        changeset.to_delete.append((class_name, live_obj.handle))
    return changeset


def _empty_counts() -> dict[str, int]:
    return {plural: 0 for plural in GRAMPS_OBJECT_PLURAL.values()}


def summarize_changeset(changeset: ResetChangeset) -> dict[str, dict[str, int]]:
    """Summarize a changeset as per-object-type counts for preview/confirmation."""
    to_add = _empty_counts()
    to_update = _empty_counts()
    to_delete = _empty_counts()
    for class_name, _obj in changeset.to_add:
        to_add[GRAMPS_OBJECT_PLURAL[class_name]] += 1
    for class_name, _obj in changeset.to_update:
        to_update[GRAMPS_OBJECT_PLURAL[class_name]] += 1
    for class_name, _handle in changeset.to_delete:
        to_delete[GRAMPS_OBJECT_PLURAL[class_name]] += 1
    return {"to_add": to_add, "to_update": to_update, "to_delete": to_delete}


def changeset_people_delta(changeset: ResetChangeset) -> int:
    """Return the net change in the number of people (for quota checks)."""
    added = sum(1 for class_name, _obj in changeset.to_add if class_name == "Person")
    deleted = sum(
        1 for class_name, _handle in changeset.to_delete if class_name == "Person"
    )
    return added - deleted


def apply_reset_changeset(
    db_handle: DbWriteBase,
    changeset: ResetChangeset,
    progress_cb: Optional[Callable] = None,
) -> None:
    """Apply a reset changeset to the live tree in a single transaction.

    Adds and updates commit the backup version of each object; deletions use the
    raw ``remove_*`` methods. Reference cleanup on delete (as in
    ``delete_object``) is deliberately not used: the backup defines a fully
    consistent target state, so once every add/update/delete is applied the tree
    matches the backup exactly.
    """
    total = len(changeset.to_add) + len(changeset.to_update) + len(changeset.to_delete)
    i = 0
    delete_handles = {handle for _class_name, handle in changeset.to_delete}
    unset_default_person = db_handle.get_default_handle() in delete_handles
    with DbTxn("Restore from backup", db_handle) as trans:
        if unset_default_person:
            db_handle.set_default_person_handle(None)
        for class_name, obj in changeset.to_add + changeset.to_update:
            if progress_cb:
                progress_cb(current=i, total=total)
            i += 1
            commit = getattr(db_handle, f"commit_{class_name.lower()}")
            commit(obj, trans)
        for class_name, handle in changeset.to_delete:
            if progress_cb:
                progress_cb(current=i, total=total)
            i += 1
            remove = getattr(db_handle, f"remove_{class_name.lower()}")
            remove(handle, trans)
