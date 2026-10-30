#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026       Doug Blank
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

"""Family link graphs kept in memory and shared between requests.

Building a `FamilyLinkGraph` reads every person and family, which takes
seconds on a large tree, while searching it takes milliseconds. Each worker
process therefore keeps the most recently used graphs, one for each tree
and for whether private records are visible, as these give different
graphs. A graph is rebuilt when the tree changes.
"""

from __future__ import annotations

import threading
from collections import OrderedDict

from gramps.gen.db import DbReadBase

from ..auth.const import PERM_VIEW_PRIVATE
from ..future_gramps.relationship_path import FamilyLinkGraph
from .auth import has_permissions
from .cache import get_db_last_change_timestamp
from .util import get_tree_from_jwt_or_fail

# the most graphs kept by a worker process
MAX_GRAPHS = 4

_GraphKey = tuple[str, float, bool]

_graphs: OrderedDict[_GraphKey, FamilyLinkGraph] = OrderedDict()
_lock = threading.Lock()


def get_family_link_graph(db_handle: DbReadBase) -> FamilyLinkGraph:
    """Return the family link graph of the current request's tree.

    `db_handle` must be the database of the current request, so that the
    graph contains what the user may see.
    """
    tree_id = get_tree_from_jwt_or_fail()
    timestamp = get_db_last_change_timestamp(tree_id)
    if timestamp is None:
        # without a change timestamp, a cached graph could be out of date
        return FamilyLinkGraph.from_db(db_handle)
    view_private = has_permissions({PERM_VIEW_PRIVATE})
    key = (tree_id, float(timestamp), view_private)
    with _lock:
        graph = _graphs.get(key)
        if graph is not None:
            _graphs.move_to_end(key)
            return graph
    graph = FamilyLinkGraph.from_db(db_handle)
    with _lock:
        # graphs of earlier versions of the tree are never used again
        for old_key in [
            old_key
            for old_key in _graphs
            if old_key[0] == tree_id and old_key[2] == view_private
        ]:
            del _graphs[old_key]
        _graphs[key] = graph
        while len(_graphs) > MAX_GRAPHS:
            _graphs.popitem(last=False)
    return graph


def clear_family_link_graphs() -> None:
    """Forget all cached graphs."""
    with _lock:
        _graphs.clear()
