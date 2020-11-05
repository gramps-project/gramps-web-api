"""Tests for the `gramps_webapi.api` module."""

import importlib
import os
import shutil
import tempfile
from unittest.mock import patch

import gramps.gen.const
import yaml
from pkg_resources import resource_filename

import gramps_webapi.app
from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EXAMPLE_GRAMPS_CONFIG

from .. import TEST_GRAMPSHOME, ExampleDbSQLite

global TEST_CLIENT, TEST_OBJECT_COUNTS


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
    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EXAMPLE_GRAMPS_CONFIG}):
        test_app = create_app(db_manager=test_db)
    test_app.config["TESTING"] = True
    TEST_CLIENT = test_app.test_client()

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


with open(resource_filename("gramps_webapi", "data/apispec.yaml")) as file_handle:
    API_SCHEMA = yaml.safe_load(file_handle)
