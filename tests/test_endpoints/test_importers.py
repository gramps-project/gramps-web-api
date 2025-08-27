#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
# Copyright (C) 2022      David M. Straub
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

"""Tests for the /api/importers endpoints."""

import io
import os
import unittest
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, set_tree_details, user_db
from gramps_webapi.auth.const import ROLE_EDITOR, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EMPTY_GRAMPS_AUTH_CONFIG

from .. import ExampleDbInMemory
from . import BASE_URL, TEST_USERS, get_test_client
from .checks import (
    check_conforms_to_schema,
    check_invalid_semantics,
    check_requires_token,
    check_resource_missing,
    check_success,
)
from .util import fetch_header

TEST_URL = BASE_URL + "/importers/"


class TestImporters(unittest.TestCase):
    """Test cases for the /api/importers endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_exporters_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_exporters_conforms_to_schema(self):
        """Test conformity to schema."""
        check_conforms_to_schema(self, TEST_URL, "Importer")

    def test_get_exporters_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "?test=1")


class TestExportersExtension(unittest.TestCase):
    """Test cases for the /api/importers/{extension} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_exporters_extension_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "gramps")

    def test_get_exporters_extension_conforms_to_schema(self):
        """Test conformity to schema."""
        check_conforms_to_schema(self, TEST_URL + "gramps", "Importer")

    def test_get_exporters_extension_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "missing")

    def test_get_exporters_extension_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "gramps?test=1")


class TestImportersExtensionFile(unittest.TestCase):
    """Test cases for the /api/exporters/{extension}/file endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.name = "empty"
        cls.dbman = CLIDbManager(DbState())
        cls.dbpath, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EMPTY_GRAMPS_AUTH_CONFIG}):
            cls.test_app = create_app(config_from_env=False, config={"TREE": cls.name})
        cls.test_app.config["TESTING"] = True
        cls.client = cls.test_app.test_client()
        cls.tree = os.path.basename(cls.dbpath)
        with cls.test_app.app_context():
            user_db.create_all()
            for role in TEST_USERS:
                add_user(
                    name=TEST_USERS[role]["name"],
                    password=TEST_USERS[role]["password"],
                    role=role,
                )

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_importers_empty_db(self):
        """Test that importers are loaded also for a fresh db."""
        rv = check_success(self, TEST_URL)
        assert len(rv) > 0

    def test_importers_wrong_role(self):
        """Test insufficient permissions."""
        headers = fetch_header(self.client, role=ROLE_EDITOR)
        rv = self.client.post(
            f"{TEST_URL}gramps/file",
            data=None,
            headers=headers,
        )
        assert rv.status_code == 403

    def test_importers_no_data(self):
        """Test missing file."""
        headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.post(
            f"{TEST_URL}gramps/file",
            data=None,
            headers=headers,
        )
        assert rv.status_code == 400
        assert "error" in rv.json
        assert "empty" in rv.json["error"]["message"]

    def test_importers_example_data(self):
        """Test importing example.gramps."""
        os.remove(os.path.join(self.dbpath, "sqlite.db"))
        example_db = ExampleDbInMemory()
        file_obj = io.BytesIO()
        with open(example_db.path, "rb") as f:
            file_obj.write(f.read())
        file_obj.seek(0)
        headers = fetch_header(self.client, role=ROLE_OWNER)
        # database has no people
        rv = check_success(self, f"{BASE_URL}/people/")
        assert len(rv) == 0
        rv = self.client.post(
            f"{TEST_URL}gramps/file",
            data=file_obj,
            headers=headers,
        )
        assert rv.status_code == 201
        # database has plenty of people
        rv = check_success(self, f"{BASE_URL}/people/")
        assert len(rv) == 2157
        # seach should work
        rv = self.client.get(f"/api/search/?query=Andrew&pagesize=5", headers=headers)
        assert len(rv.json) == 5
        # import again
        file_obj.seek(0)
        rv = self.client.post(
            f"{TEST_URL}gramps/file",
            data=file_obj,
            headers=headers,
        )
        assert rv.status_code == 201
        # everything doubled
        rv = check_success(self, f"{BASE_URL}/people/")
        assert len(rv) == 2 * 2157

    def test_importers_example_data_quota(self):
        """Test importing example.gramps with a quota."""
        os.remove(os.path.join(self.dbpath, "sqlite.db"))
        with self.test_app.app_context():
            set_tree_details(self.tree, quota_people=2000)
        example_db = ExampleDbInMemory()
        file_obj = io.BytesIO()
        with open(example_db.path, "rb") as f:
            file_obj.write(f.read())
        file_obj.seek(0)
        headers = fetch_header(self.client, role=ROLE_OWNER)
        # database has no people
        rv = check_success(self, f"{BASE_URL}/people/")
        assert len(rv) == 0
        rv = self.client.post(
            f"{TEST_URL}gramps/file",
            data=file_obj,
            headers=headers,
        )
        assert rv.status_code == 500
        rv = check_success(self, f"{BASE_URL}/people/")
        assert len(rv) == 0
        with self.test_app.app_context():
            set_tree_details(self.tree, quota_people=None)
