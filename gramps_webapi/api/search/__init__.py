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

"""Full-text search utilities."""

import os

from flask import current_app

from .indexer import SearchIndexer


def get_search_indexer(tree: str) -> SearchIndexer:
    """Get the search indexer for the tree."""
    base_dir = current_app.config["SEARCH_INDEX_DIR"]
    index_dir = os.path.join(base_dir, tree)
    return SearchIndexer(index_dir=index_dir)
