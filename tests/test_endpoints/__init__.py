#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Tests for the `gramps_webapi.api` module."""

import importlib
import os
import shutil
import tempfile
from unittest.mock import patch

import gramps.gen.const
import yaml
from jsonschema import RefResolver
from pkg_resources import resource_filename

import gramps_webapi.app
from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EXAMPLE_GRAMPS_AUTH_CONFIG
from tests import TEST_GRAMPSHOME, ExampleDbSQLite

with open(resource_filename("gramps_webapi", "data/apispec.yaml")) as file_handle:
    API_SCHEMA = yaml.safe_load(file_handle)

API_RESOLVER = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})

BASE_URL = "/api"
TEST_USER = "user"
TEST_PASSWORD = "123"


def get_object_count(gramps_object):
    """Return count for an object type in database."""
    return TEST_OBJECT_COUNTS[gramps_object]


def get_test_client():
    """Return test client."""
    return TEST_CLIENT


def setUpModule():
    """Test module setup."""
    global TEST_CLIENT, TEST_OBJECT_COUNTS

    test_db = ExampleDbSQLite()
    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EXAMPLE_GRAMPS_AUTH_CONFIG}):
        test_app = create_app(db_manager=test_db)
    test_app.config["TESTING"] = True
    TEST_CLIENT = test_app.test_client()
    sqlauth = test_app.config["AUTH_PROVIDER"]
    sqlauth.create_table()
    sqlauth.add_user(name=TEST_USER, password=TEST_PASSWORD)

    db_state = test_app.config["DB_MANAGER"].get_db()
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


def tearDownModule():
    """Test module tear down."""
    if TEST_GRAMPSHOME and os.path.isdir(TEST_GRAMPSHOME):
        shutil.rmtree(TEST_GRAMPSHOME)
