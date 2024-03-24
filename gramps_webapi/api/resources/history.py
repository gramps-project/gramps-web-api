#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2024      David Straub
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

"""Database Transaction history endpoints."""

from typing import Dict

from flask import Response
from gramps.gen.db.dbconst import TXNADD, TXNDEL, TXNUPD
from webargs import fields

from ..util import get_db_handle, use_args
from . import ProtectedResource

trans_code = {"delete": TXNDEL, "add": TXNADD, "update": TXNUPD}


class TransactionsHistoryResource(ProtectedResource):
    """Resource for database transaction history."""

    @use_args(
        {
            "old": fields.Boolean(load_default=False),
            "new": fields.Boolean(load_default=False),
            "patch": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def get(self, args: Dict) -> Response:
        """Return a list of transactions."""
        db_handle = get_db_handle()
        transactions = []
        undodb = db_handle.undodb
        transactions = undodb.get_transactions(
            old_data=args["old"], new_data=args["new"], patch=args["patch"]
        )
        return transactions
