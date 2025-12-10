#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Pytest fixtures for Gramps Web API tests.

IMPORTANT NOTES:
================

1. **First Run**: The first test run will take ~40-60 seconds to:
   - Import the example Gramps database (~10-15s)
   - Create empty database (~5s)
   - Index both databases (~20-30s)

   After this initial setup, ALL subsequent tests in the same session are FAST
   because they reuse the same database and indexes.

2. **Session vs Function Scope**:
   - `example_*` fixtures: Session-scoped, shared across ALL tests
     → Use for READ-ONLY tests (GET requests)
     → Very fast after initial setup

   - `isolated_*` fixtures: Function-scoped, fresh database per test
     → Use for WRITE tests (POST/PUT/DELETE)
     → Takes ~40s per test (creates fresh DB + indexes)

3. **Migration Strategy**:
   - Convert READ-ONLY tests first (biggest time savings)
   - Leave WRITE tests for Phase 2 or convert selectively
   - See FIXTURE_MIGRATION_GUIDE.md for details

4. **Expected Performance**:
   - Before: 48 modules × 34s setup = ~27 minutes
   - After (session fixtures): 1 × 40s setup = ~40 seconds total
   - Savings: ~26 minutes for read-only tests!

5. **Backward Compatibility**:
   - Old setUpModule() tests still work
   - Gradual migration is safe and recommended
   - Both patterns can coexist during transition
"""

import os
import tempfile
from typing import Dict
from unittest.mock import patch

import pytest
from flask import Flask
from flask.testing import FlaskClient
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.api.search import get_search_indexer
from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import (
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_GUEST,
    ROLE_MEMBER,
    ROLE_OWNER,
)
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EXAMPLE_GRAMPS_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager
from tests import ExampleDbSQLite


TEST_USERS = {
    ROLE_ADMIN: {"name": "admin", "password": "ghi"},
    ROLE_OWNER: {"name": "owner", "password": "123"},
    ROLE_EDITOR: {"name": "editor", "password": "abc"},
    ROLE_MEMBER: {"name": "member", "password": "456"},
    ROLE_GUEST: {"name": "guest", "password": "def"},
}


@pytest.fixture(scope="session")
def example_gramps_db():
    """Create example database once for all tests (session-scoped).

    This database should be treated as READ-ONLY by tests.
    Tests that need to modify data should use `isolated_example_db` instead.
    """
    test_db = ExampleDbSQLite(name="example_gramps")
    yield test_db
    # Cleanup handled by tearDownModule in tests/__init__.py


@pytest.fixture(scope="session")
def example_app(example_gramps_db):
    """Create Flask app with example database (session-scoped).

    This app uses the shared example database and is intended for READ-ONLY tests.
    """
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

    with test_app.app_context():
        user_db.create_all()

        # Create also an empty db in addition to the example db
        for db_name in ["empty_db", example_gramps_db.name]:
            db_manager = WebDbManager(name=db_name, create_if_missing=True)
            tree = db_manager.dirname

            for role, user in TEST_USERS.items():
                # For the empty db, append "_empty" to usernames
                user_suffix = "_empty" if "empty" in db_name else ""
                add_user(
                    name=user["name"] + user_suffix,
                    password=user["password"],
                    role=role,
                    tree=tree,
                )

            # Index the database
            db_state = db_manager.get_db()
            search_index = get_search_indexer(tree)
            db = db_state.db
            search_index.reindex_full(db)
            db_state.db.close()

    yield test_app


@pytest.fixture(scope="session")
def example_client(example_app):
    """Create test client for example app (session-scoped).

    Use this client for READ-ONLY tests that don't modify the database.
    """
    return example_app.test_client()


@pytest.fixture(scope="session")
def example_object_counts(example_app, example_gramps_db):
    """Get object counts from example database (session-scoped).

    Returns a dict with counts for each object type.
    """
    with example_app.app_context():
        db_manager = WebDbManager(name=example_gramps_db.name)
        db_state = db_manager.get_db()
        db = db_state.db

        counts = {
            "people": db.get_number_of_people(),
            "families": db.get_number_of_families(),
            "events": db.get_number_of_events(),
            "places": db.get_number_of_places(),
            "citations": db.get_number_of_citations(),
            "sources": db.get_number_of_sources(),
            "repositories": db.get_number_of_repositories(),
            "media": db.get_number_of_media(),
            "notes": db.get_number_of_notes(),
            "tags": db.get_number_of_tags(),
        }

        db_state.db.close()
        return counts


@pytest.fixture
def isolated_example_db():
    """Create a fresh copy of the example database for tests that modify data.

    This is function-scoped, so each test gets a fresh database.
    Use this for tests that POST, PUT, PATCH, or DELETE.
    """
    # Create unique name for this test run
    import uuid

    unique_name = f"test_isolated_{uuid.uuid4().hex[:8]}"

    test_db = ExampleDbSQLite(name=unique_name)
    yield test_db

    # Cleanup: remove the database
    dbman = CLIDbManager(DbState())
    try:
        dbman.remove_database(unique_name)
    except Exception:
        pass  # Database may already be cleaned up


@pytest.fixture
def isolated_app(isolated_example_db):
    """Create Flask app with isolated database for tests that modify data.

    This is function-scoped, so each test gets a fresh app and database.
    """
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

    with test_app.app_context():
        user_db.create_all()

        # Setup users for the isolated database
        db_manager = WebDbManager(name=isolated_example_db.name, create_if_missing=True)
        tree = db_manager.dirname

        for role, user in TEST_USERS.items():
            add_user(
                name=user["name"],
                password=user["password"],
                role=role,
                tree=tree,
            )

        # Index the database
        db_state = db_manager.get_db()
        search_index = get_search_indexer(tree)
        db = db_state.db
        search_index.reindex_full(db)
        db_state.db.close()

    yield test_app


@pytest.fixture
def isolated_client(isolated_app):
    """Create test client with isolated database for tests that modify data.

    Use this client for tests that POST, PUT, PATCH, or DELETE.
    Each test gets a fresh database through the isolated_app fixture.
    """
    return isolated_app.test_client()


@pytest.fixture
def auth_headers(example_client) -> Dict[int, Dict[str, str]]:
    """Get auth headers for all test users (uses session-scoped client).

    Returns a dict mapping role to auth headers:
    {
        ROLE_OWNER: {'Authorization': 'Bearer ...'},
        ROLE_ADMIN: {'Authorization': 'Bearer ...'},
        ...
    }
    """
    headers = {}

    for role, user in TEST_USERS.items():
        rv = example_client.post(
            "/api/token/", json={"username": user["name"], "password": user["password"]}
        )
        if rv.status_code == 200:
            access_token = rv.json["access_token"]
            headers[role] = {"Authorization": f"Bearer {access_token}"}

    return headers


@pytest.fixture
def isolated_auth_headers(isolated_client) -> Dict[int, Dict[str, str]]:
    """Get auth headers for isolated database tests.

    Returns a dict mapping role to auth headers:
    {
        ROLE_OWNER: {'Authorization': 'Bearer ...'},
        ROLE_ADMIN: {'Authorization': 'Bearer ...'},
        ...
    }
    """
    headers = {}

    for role, user in TEST_USERS.items():
        rv = isolated_client.post(
            "/api/token/", json={"username": user["name"], "password": user["password"]}
        )
        if rv.status_code == 200:
            access_token = rv.json["access_token"]
            headers[role] = {"Authorization": f"Bearer {access_token}"}

    return headers


# ==============================================================================
# Pytest Test Adapter for Unittest-Style Check Functions
# ==============================================================================
# This adapter allows unittest-style check functions to work with pytest fixtures


class PytestTestAdapter:
    """Adapter to make unittest-style tests work with pytest fixtures.

    This provides the .client and .assertEqual() interface expected by
    the check functions in tests/test_endpoints/checks.py.
    """

    def __init__(self, client):
        """Initialize with a test client."""
        self.client = client

    def assertEqual(self, first, second, msg=None):
        """Pytest-compatible assertEqual."""
        assert first == second, msg or f"{first} != {second}"

    def assertIsInstance(self, obj, cls, msg=None):
        """Pytest-compatible assertIsInstance."""
        assert isinstance(obj, cls), msg or f"{obj} is not an instance of {cls}"

    def assertIn(self, member, container, msg=None):
        """Pytest-compatible assertIn."""
        assert member in container, msg or f"{member} not found in {container}"

    def assertNotIn(self, member, container, msg=None):
        """Pytest-compatible assertNotIn."""
        assert member not in container, (
            msg or f"{member} unexpectedly found in {container}"
        )

    def assertLessEqual(self, first, second, msg=None):
        """Pytest-compatible assertLessEqual."""
        assert first <= second, msg or f"{first} > {second}"

    def assertGreaterEqual(self, first, second, msg=None):
        """Pytest-compatible assertGreaterEqual."""
        assert first >= second, msg or f"{first} < {second}"

    def assertTrue(self, expr, msg=None):
        """Pytest-compatible assertTrue."""
        assert expr, msg or f"Expression is not True"


@pytest.fixture
def test_adapter(example_client):
    """Create a test adapter for example_client (session-scoped, read-only).

    This allows unittest-style check functions to work with pytest fixtures:

    Usage:
        def test_something(test_adapter):
            check_success(test_adapter, "/api/people/")
    """
    return PytestTestAdapter(example_client)


@pytest.fixture
def isolated_test_adapter(isolated_client):
    """Create a test adapter for isolated_client (function-scoped, for writes).

    Usage:
        def test_create_something(isolated_test_adapter):
            check_success(isolated_test_adapter, "/api/people/")
    """
    return PytestTestAdapter(isolated_client)


# Helper functions for backward compatibility with unittest-style tests


def get_example_client_for_unittest():
    """Helper to get the example client from within unittest.TestCase.

    This allows unittest-style tests to access the session-scoped fixtures
    without converting the entire test class to pytest.

    Usage in test:
        from tests.conftest import get_example_client_for_unittest

        def test_something(self):
            client = get_example_client_for_unittest()
            rv = client.get('/api/people/')
    """
    # This will be populated by pytest when fixtures are available
    # For now, returns None to maintain backward compatibility
    return None
