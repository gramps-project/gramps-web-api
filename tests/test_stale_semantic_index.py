#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

"""Tests for changes to a tree whose semantic index was built with another model."""

import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.api.search import _get_search_index_db_url
from gramps_webapi.api.search.metadata import (
    get_stored_model_name,
    set_stored_model_name,
)
from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG

RESTORE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.2//EN"
"http://gramps-project.org/xml/1.7.2/grampsxml.dtd">
<database xmlns="http://gramps-project.org/xml/1.7.2/">
  <header><created date="2026-01-01" version="6.0"/></header>
  <people>
    <person handle="_restoredperson" change="0" id="I9001">
      <gender>U</gender>
      <name type="Birth Name">
        <first>Restorefindable</first>
        <surname>Stale</surname>
      </name>
    </person>
  </people>
</database>
"""


class FakeModel:
    """Stand-in for a sentence transformer model."""

    def encode(self, texts):
        return [[float(len(text)), 1.0] for text in texts]


def make_person(given: str) -> dict:
    return {
        "_class": "Person",
        "handle": str(uuid.uuid4()),
        "primary_name": {
            "_class": "Name",
            "first_name": given,
            "surname_list": [{"_class": "Surname", "surname": "Stale"}],
        },
    }


class TestStaleSemanticIndex(unittest.TestCase):
    """Changes must succeed while the semantic index waits for a full reindex."""

    @classmethod
    def setUpClass(cls):
        cls.name = "Stale Semantic Index"
        cls.dbman = CLIDbManager(DbState())
        dirpath, _ = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        cls.tree = os.path.basename(dirpath)
        cls.index_dir = tempfile.TemporaryDirectory()
        with (
            patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}),
            patch("gramps_webapi.app.load_model", return_value=FakeModel()),
        ):
            cls.app = create_app(
                config={
                    "TESTING": True,
                    "VECTOR_EMBEDDING_MODEL": "new-model",
                    "SEARCH_INDEX_DB_URI": f"sqlite:///{cls.index_dir.name}/index.db",
                },
                config_from_env=False,
            )
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="owner", password="123", role=ROLE_OWNER, tree=cls.tree)
            cls.db_url = _get_search_index_db_url()
            set_stored_model_name(cls.db_url, cls.tree, "old-model")
        rv = cls.client.post(
            "/api/token/", json={"username": "owner", "password": "123"}
        )
        cls.headers = {"Authorization": f"Bearer {rv.json['access_token']}"}

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)
        cls.index_dir.cleanup()

    def add_person(self, given: str) -> str:
        person = make_person(given)
        rv = self.client.post("/api/people/", json=person, headers=self.headers)
        self.assertEqual(rv.status_code, 201)
        return person["handle"]

    def test_edit_succeeds(self):
        handle = self.add_person("Edited")
        rv = self.client.get(f"/api/people/{handle}", headers=self.headers)
        person = rv.json
        person["gender"] = 1
        rv = self.client.put(f"/api/people/{handle}", json=person, headers=self.headers)
        self.assertEqual(rv.status_code, 200)

    def test_delete_succeeds(self):
        handle = self.add_person("Deleted")
        rv = self.client.delete(f"/api/people/{handle}", headers=self.headers)
        self.assertEqual(rv.status_code, 200)

    def test_merge_succeeds(self):
        phoenix = self.add_person("Phoenix")
        titanic = self.add_person("Titanic")
        rv = self.client.post(
            f"/api/people/{phoenix}/merge/{titanic}", headers=self.headers
        )
        self.assertEqual(rv.status_code, 200)

    def test_full_text_index_is_still_updated(self):
        self.add_person("Fulltextfindable")
        rv = self.client.get(
            "/api/search/?query=Fulltextfindable", headers=self.headers
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(len(rv.json), 1)

    def count_full_text_hits(self, query: str) -> int:
        rv = self.client.get(f"/api/search/?query={query}", headers=self.headers)
        self.assertEqual(rv.status_code, 200)
        return len(rv.json)

    def assert_stored_model_unchanged(self):
        self.assertEqual(get_stored_model_name(self.db_url, self.tree), "old-model")

    def test_import_succeeds(self):
        gedcom = (
            "0 HEAD\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME Importfindable /Stale/\n0 TRLR\n"
        )
        rv = self.client.post(
            "/api/importers/ged/file", data=gedcom.encode(), headers=self.headers
        )
        self.assertEqual(rv.status_code, 201)
        self.assertEqual(self.count_full_text_hits("Importfindable"), 1)
        self.assert_stored_model_unchanged()

    def test_restore_succeeds(self):
        rv = self.client.post(
            "/api/importers/gramps/file/restore",
            data=RESTORE_XML.encode(),
            headers=self.headers,
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(self.count_full_text_hits("Restorefindable"), 1)
        self.assert_stored_model_unchanged()

    def test_bulk_delete_succeeds(self):
        self.add_person("Bulkdeleted")
        self.assertEqual(self.count_full_text_hits("Bulkdeleted"), 1)
        rv = self.client.post("/api/objects/delete/", headers=self.headers)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(self.count_full_text_hits("Bulkdeleted"), 0)
        self.assert_stored_model_unchanged()

    def test_semantic_search_still_reports_stale_index(self):
        rv = self.client.get(
            "/api/search/?query=anything&semantic=1", headers=self.headers
        )
        self.assertEqual(rv.status_code, 503)

    def test_stored_model_is_unchanged(self):
        self.add_person("Unchanged")
        self.assertEqual(get_stored_model_name(self.db_url, self.tree), "old-model")
