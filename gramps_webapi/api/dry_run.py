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

"""Dry runs of database changes."""

from __future__ import annotations

from collections.abc import Callable

from gramps.gen.db import DbTxn
from gramps.gen.db.base import DbWriteBase

from ..types import TransactionJson
from .resources.util import transaction_to_json
from .util import close_db, get_db_outside_request


def dry_run(
    tree: str,
    user_id: str,
    apply: Callable[[DbWriteBase, DbTxn], None],
) -> TransactionJson:
    """Apply changes in a transaction, roll it back and return it as JSON.

    `apply` must not commit transactions itself (as importers do), as that
    would commit the dry run too.

    The result includes side effects, e.g. on the parents of a new family,
    and private records; filter it for users who may not view these.

    Uses its own database handle, closed without writing Gramps's in-memory
    state (e.g. new custom types), which the rollback does not undo.
    """
    db = get_db_outside_request(
        tree=tree, view_private=True, readonly=False, user_id=user_id
    )
    trans = DbTxn("Dry run", db)
    db.transaction_begin(trans)
    try:
        apply(db, trans)
        return transaction_to_json(trans)
    finally:
        db.transaction_abort(trans)
        close_db(db, update=False)
