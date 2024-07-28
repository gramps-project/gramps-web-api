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

import warnings
from pathlib import Path
from urllib.parse import urlparse

from flask import current_app

from .indexer import SearchIndexer


def get_search_indexer(tree: str) -> SearchIndexer:
    """Get the search indexer for the tree."""
    db_url = current_app.config["SEARCH_INDEX_DB_URI"] or None
    if not db_url and current_app.config["SEARCH_INDEX_DIR"]:
        # backwards compatibility...
        db_url = f"sqlite:///{current_app.config['SEARCH_INDEX_DIR']}/search_index.db"
        warnings.warn(
            "The SEARCH_INDEX_DIR config option is deprecated and will be removed in a "
            "future release. Please use SEARCH_INDEX_DB_URI instead, "
            f"e.g. setting it to {db_url}"
        )
    url_parts = urlparse(db_url)
    # in case of SQLite create the containing directory if it doesn't exist
    if url_parts.scheme == "sqlite":
        path = url_parts.path
        if path.lstrip("/") and path.lstrip("/") != ":memory:" and path[0] == "/":
            path = Path(path[1:])
            if not path.exists() and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)

    return SearchIndexer(db_url=db_url, tree=tree)
