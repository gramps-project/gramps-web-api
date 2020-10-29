"""Tests for the `gramps_webapi.api` module."""

from unittest.mock import patch

import yaml
from pkg_resources import resource_filename

from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EXAMPLE_GRAMPS_CONFIG

from .. import ExampleDbInMemory, ExampleDbSQLite

global TEST_DB, TEST_APP, TEST_CLIENT, TEST_OBJECT_COUNTS


def get_object_count(gramps_object):
    """Return number of object type in database."""
    return TEST_OBJECT_COUNTS[gramps_object]


def get_test_client():
    """Return test client."""
    return TEST_CLIENT


def setUpModule():
    """Test module setup."""
    global TEST_DB, TEST_APP, TEST_CLIENT, TEST_OBJECT_COUNTS
    TEST_DB = ExampleDbInMemory()
    TEST_DB.load()
    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EXAMPLE_GRAMPS_CONFIG}):
        TEST_APP = create_app()
    TEST_APP.config["TESTING"] = True
    TEST_CLIENT = TEST_APP.test_client()

    db_manager = TEST_APP.config["DB_MANAGER"]
    db_state = db_manager.get_db()
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
    TEST_DB.close()


with open(resource_filename("gramps_webapi", "data/apispec.yaml")) as file_handle:
    API_SCHEMA = yaml.safe_load(file_handle)
