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

"""Tests for the `gramps_webapi.api` module."""

import os
import shutil
from unittest.mock import patch

import yaml
from jsonschema import RefResolver
from pkg_resources import resource_filename

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
from tests import TEST_GRAMPSHOME, ExampleDbSQLite

with open(resource_filename("gramps_webapi", "data/apispec.yaml")) as file_handle:
    API_SCHEMA = yaml.safe_load(file_handle)

API_RESOLVER = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})

BASE_URL = "/api"

TEST_USERS = {
    ROLE_ADMIN: {"name": "admin", "password": "ghi"},
    ROLE_OWNER: {"name": "owner", "password": "123"},
    ROLE_EDITOR: {"name": "editor", "password": "abc"},
    ROLE_MEMBER: {"name": "member", "password": "456"},
    ROLE_GUEST: {"name": "guest", "password": "def"},
}


def get_object_count(gramps_object):
    """Return count for an object type in database."""
    return TEST_OBJECT_COUNTS[gramps_object]


def get_test_client():
    """Return test client."""
    return TEST_CLIENT


def setUpModule():
    """Test module setup."""
    global TEST_CLIENT, TEST_OBJECT_COUNTS

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
            search_index.reindex_full(db)
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
