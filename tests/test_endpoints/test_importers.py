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
        db_file = os.path.join(self.dbpath, "sqlite.db")
        if os.path.exists(db_file):
            os.remove(db_file)
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
        db_file = os.path.join(self.dbpath, "sqlite.db")
        if os.path.exists(db_file):
            os.remove(db_file)
        with self.test_app.app_context():
            set_tree_details(self.tree, quota_people=2000)
        example_db = ExampleDbInMemory()
        file_obj = io.BytesIO()
        with open(example_db.path, "rb") as f:
            file_obj.write(f.read())
        file_obj.seek(0)
        headers = fetch_header(self.client, role=ROLE_OWNER)
        # Check current people count
        rv = check_success(self, f"{BASE_URL}/people/")
        people_before = len(rv)
        rv = self.client.post(
            f"{TEST_URL}gramps/file",
            data=file_obj,
            headers=headers,
        )
        assert rv.status_code == 500
        # Verify nothing was imported due to quota
        rv = check_success(self, f"{BASE_URL}/people/")
        assert len(rv) == people_before
        with self.test_app.app_context():
            set_tree_details(self.tree, quota_people=None)


class TestImportersGedcom(unittest.TestCase):
    """Test cases for GEDCOM import functionality."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.name = "gedcom_test"
        cls.dbman = CLIDbManager(DbState())
        cls.dbpath, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
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

    def test_importers_gedcom7_file(self):
        """Test importing a GEDCOM 7 file."""
        # Create a sample GEDCOM 7 file
        gedcom7_content = b"""0 HEAD
1 GEDC
2 VERS 7.0
0 @I1@ INDI
1 NAME John /Doe/
2 GIVN John
2 SURN Doe
1 SEX M
1 BIRT
2 DATE 1 JAN 1950
0 @I2@ INDI
1 NAME Jane /Smith/
2 GIVN Jane
2 SURN Smith
1 SEX F
1 BIRT
2 DATE 15 MAR 1952
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 10 JUN 1975
0 TRLR
"""
        file_obj = io.BytesIO(gedcom7_content)
        headers = fetch_header(self.client, role=ROLE_OWNER)
        # Get current counts
        rv = check_success(self, f"{BASE_URL}/people/")
        people_before = len(rv)
        rv = check_success(self, f"{BASE_URL}/families/")
        families_before = len(rv)
        # import GEDCOM 7 file
        rv = self.client.post(
            f"{TEST_URL}ged/file",
            data=file_obj,
            headers=headers,
        )
        assert rv.status_code == 201
        # database should have 2 more people
        rv = check_success(self, f"{BASE_URL}/people/")
        assert len(rv) == people_before + 2
        # database should have 1 more family
        rv = check_success(self, f"{BASE_URL}/families/")
        assert len(rv) == families_before + 1

    def test_importers_gedcom55_file(self):
        """Test importing a GEDCOM 5.5 file."""
        # Create a sample GEDCOM 5.5 file
        gedcom55_content = b"""0 HEAD
1 SOUR Test
1 GEDC
2 VERS 5.5
2 FORM LINEAGE-LINKED
0 @I1@ INDI
1 NAME Alice /Brown/
1 SEX F
1 BIRT
2 DATE 25 DEC 1960
0 @I2@ INDI
1 NAME Bob /Brown/
1 SEX M
0 TRLR
"""
        file_obj = io.BytesIO(gedcom55_content)
        headers = fetch_header(self.client, role=ROLE_OWNER)
        # Get current count of people
        rv = check_success(self, f"{BASE_URL}/people/")
        people_before = len(rv)
        # import GEDCOM 5.5 file
        rv = self.client.post(
            f"{TEST_URL}ged/file",
            data=file_obj,
            headers=headers,
        )
        assert rv.status_code == 201
        # database should have 2 more people
        rv = check_success(self, f"{BASE_URL}/people/")
        assert len(rv) == people_before + 2

    def test_importers_gedcom7_with_events(self):
        """Test importing a GEDCOM 7 file with events."""
        # Create a GEDCOM 7 file with various events
        gedcom7_content = b"""0 HEAD
1 GEDC
2 VERS 7.0
0 @I1@ INDI
1 NAME Mary /Johnson/
2 GIVN Mary
2 SURN Johnson
1 SEX F
1 BIRT
2 DATE 5 FEB 1945
2 PLAC London, England
1 DEAT
2 DATE 20 JUL 2020
2 PLAC Manchester, England
0 @E1@ EVEN
1 TYPE Military Service
1 DATE 1963
0 TRLR
"""
        file_obj = io.BytesIO(gedcom7_content)
        headers = fetch_header(self.client, role=ROLE_OWNER)
        # Get current counts
        rv = check_success(self, f"{BASE_URL}/people/")
        people_before = len(rv)
        rv = check_success(self, f"{BASE_URL}/events/")
        events_before = len(rv)
        # import GEDCOM 7 file
        rv = self.client.post(
            f"{TEST_URL}ged/file",
            data=file_obj,
            headers=headers,
        )
        assert rv.status_code == 201
        # verify person was imported
        rv = check_success(self, f"{BASE_URL}/people/")
        assert len(rv) == people_before + 1
        # verify events were imported (at least birth and death)
        rv = check_success(self, f"{BASE_URL}/events/")
        assert len(rv) >= events_before + 2
