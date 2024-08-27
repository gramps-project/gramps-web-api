#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2024 David Straub
# Copyright (C) 2020      Christopher Horn
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

"""Test full-text search."""

import shutil
import tempfile
import unittest
from urllib.parse import quote

from gramps_webapi.api.search import SemanticSearchIndexer
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER
from gramps_webapi.dbmanager import WebDbManager

from . import BASE_URL, get_test_client
from .checks import (
    check_invalid_semantics,
    check_requires_token,
    check_strip_parameter,
    check_success,
)
from .util import fetch_header

TEST_URL = BASE_URL + "/search/"


def embedding_function(contents):
    return [1, 2, 3]


class TestSemanticSearch(unittest.TestCase):
    """Test cases for semantic search."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        cls.index_dir = tempfile.mkdtemp()
        cls.dbmgr = WebDbManager(name="example_gramps", create_if_missing=False)
        tree = cls.dbmgr.dirname
        db_url = f"sqlite:///{cls.index_dir}/search_index.db"
        cls.search = SemanticSearchIndexer(tree, db_url, embedding_function)
        db = cls.dbmgr.get_db().db
        cls.search.reindex_full(db)
        db.close()

    @classmethod
    def tearDownClass(cls):
        """Remove the temporary index directory."""
        shutil.rmtree(cls.index_dir)

    def test_nothing(self):
        pass
