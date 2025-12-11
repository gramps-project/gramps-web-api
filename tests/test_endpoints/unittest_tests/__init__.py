#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
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

"""Setup module for unittest-based tests.

This module contains the setUpModule() function that creates databases
and initializes global state for unittest-based tests.

IMPORTANT: This module is ONLY for unittest-based tests. Pytest-based tests
use session-scoped fixtures in conftest.py instead.

TODO: Delete this entire file once all tests are converted to pytest.
"""

import os
from unittest.mock import patch

from gramps_webapi.api.search import get_search_indexer
from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EXAMPLE_GRAMPS_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager
from tests import ExampleDbSQLite

from .. import TEST_USERS, BASE_URL, API_SCHEMA, API_RESOLVER

# Import roles used by tests
from gramps_webapi.auth.const import (
    ROLE_GUEST,
    ROLE_MEMBER,
    ROLE_OWNER,
    ROLE_EDITOR,
    ROLE_ADMIN,
)

# Import checks module so unittest tests can use: from . import checks
from .. import checks

# Global state for unittest tests (initialized by setUpModule)
TEST_CLIENT = None
TEST_OBJECT_COUNTS = None


def get_object_count(gramps_object):
    """Return count for an object type in database.

    Used by unittest-based tests. Pytest tests should use the
    example_object_counts fixture instead.
    """
    return TEST_OBJECT_COUNTS[gramps_object]


def get_test_client():
    """Return test client.

    Used by unittest-based tests. Pytest tests should use the
    test_adapter fixture instead.
    """
    return TEST_CLIENT


def setUpModule():
    """Test module setup for unittest-based tests.

    This function creates:
    - Example Gramps database
    - Empty database
    - Test users for both databases
    - Search indexes for both databases
    - Flask test client

    This setup takes ~40 seconds and is called once per unittest test module.

    NOTE: Pytest-based tests do NOT use this function. They use session-scoped
    fixtures in conftest.py instead, which run once for ALL tests (~40s total).

    TODO: Delete this function once all tests are converted to pytest.
    """
    import time

    global TEST_CLIENT, TEST_OBJECT_COUNTS

    start = time.time()
    print(f"\n[SETUP] Unittest setUpModule starting...", flush=True)

    # create a database with the Gramps example tree
    test_db = ExampleDbSQLite(name="example_gramps")

    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EXAMPLE_GRAMPS_AUTH_CONFIG}):
        test_app = create_app(
            config={
                "TESTING": True,
                "RATELIMIT_ENABLED": False,
                "MEDIA_BASE_DIR": f"{os.environ['GRAMPS_RESOURCES']}/doc/gramps/example/gramps",
                "VECTOR_EMBEDDING_MODEL": "paraphrase-albert-small-v2",
                "LLM_MODEL": "mock-model",
            },
            config_from_env=False,
        )
    TEST_CLIENT = test_app.test_client()
    with test_app.app_context():
        user_db.create_all()

        # create also an empty db in addition to the example db
        for db_name in "empty_db", test_db.name:
            db_manager = WebDbManager(name=db_name, create_if_missing=True)
            tree = db_manager.dirname

            for role, user in TEST_USERS.items():
                # for the empty db, append "_empty" to usernames
                user_suffix = "_empty" if "empty" in db_name else ""
                add_user(
                    name=user["name"] + user_suffix,
                    password=user["password"],
                    role=role,
                    tree=tree,
                )

            db_state = db_manager.get_db()
            search_index = get_search_indexer(tree)
            db = db_state.db
            index_start = time.time()
            search_index.reindex_full(db)
            index_elapsed = time.time() - index_start
            print(f"[SETUP] {db_name}: indexed in {index_elapsed:.1f}s", flush=True)
    TEST_OBJECT_COUNTS = {
        "people": db_state.db.get_number_of_people(),
        "families": db_state.db.get_number_of_families(),
        "events": db_state.db.get_number_of_events(),
        "places": db_state.db.get_number_of_places(),
        "citations": db_state.db.get_number_of_citations(),
        "sources": db_state.db.get_number_of_sources(),
        "repositories": db_state.db.get_number_of_repositories(),
        "media": db_state.db.get_number_of_media(),
        "notes": db_state.db.get_number_of_notes(),
        "tags": db_state.db.get_number_of_tags(),
    }
    db_state.db.close()

    elapsed = time.time() - start
    print(f"[SETUP] Unittest setUpModule complete in {elapsed:.1f}s", flush=True)
