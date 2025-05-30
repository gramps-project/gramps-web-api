#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2024      David Straub
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

"""Tests transaction history endpoint."""

import os
import unittest
from typing import Dict
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import (
    ROLE_CONTRIBUTOR,
    ROLE_EDITOR,
    ROLE_GUEST,
    ROLE_MEMBER,
    ROLE_OWNER,
)
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EMPTY_GRAMPS_AUTH_CONFIG


def get_headers(client, user: str, password: str) -> Dict[str, str]:
    """Get the auth headers for a specific user."""
    rv = client.post("/api/token/", json={"username": user, "password": password})
    access_token = rv.json["access_token"]
    return {"Authorization": "Bearer {}".format(access_token)}


class TestTransactionHistoryResource(unittest.TestCase):
    def setUp(self):
        self.name = "Test Web API History"
        self.dbman = CLIDbManager(DbState())
        dirpath, _ = self.dbman.create_new_db_cli(self.name, dbid="sqlite")
        tree = os.path.basename(dirpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EMPTY_GRAMPS_AUTH_CONFIG}):
            self.app = create_app(config_from_env=False, config={"TREE": self.name})
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.app.app_context():
            user_db.create_all()
            add_user(name="user", password="123", role=ROLE_GUEST, tree=tree)
            add_user(name="admin", password="123", role=ROLE_OWNER, tree=tree)
            add_user(name="member", password="123", role=ROLE_MEMBER, tree=tree)
            add_user(name="editor", password="123", role=ROLE_EDITOR, tree=tree)
            add_user(
                name="contributor", password="123", role=ROLE_CONTRIBUTOR, tree=tree
            )

    def tearDown(self):
        self.dbman.remove_database(self.name)

    def test_add_single(self):
        headers = get_headers(self.client, "editor", "123")
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        assert rv.json == []
        rv = self.client.post("/api/people/", json={}, headers=headers)
        assert rv.status_code == 201
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        assert len(transactions) == 1
        transaction = transactions[0]
        assert transaction["id"] == 1
        assert transaction["first"] == 1
        assert transaction["last"] == 1
        assert transaction["connection"]["id"] == 1
        assert transaction["connection"]["user"]["name"] == "editor"
        assert len(transaction["changes"]) == 1
        change = transaction["changes"][0]
        assert change["id"] == 1
        assert change["obj_class"] == "Person"
        assert change["trans_type"] == 0
        assert "old_data" not in change
        assert "new_data" not in change

    def test_add_two(self):
        headers = get_headers(self.client, "editor", "123")
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        assert rv.json == []
        objects = [
            {"_class": "Person"},
            {"_class": "Person"},
        ]
        rv = self.client.post("/api/objects/", json=objects, headers=headers)
        assert rv.status_code == 201
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        assert len(transactions) == 1
        transaction = transactions[0]
        assert transaction["id"] == 1
        assert transaction["first"] == 1
        assert transaction["last"] == 2
        assert transaction["connection"]["id"] == 1
        assert len(transaction["changes"]) == 2
        for change in transaction["changes"]:
            assert change["obj_class"] == "Person"
            assert change["trans_type"] == 0

    def test_add_one_plus_one(self):
        headers = get_headers(self.client, "editor", "123")
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        assert rv.json == []
        rv = self.client.post("/api/people/", json={}, headers=headers)
        assert rv.status_code == 201
        rv = self.client.post("/api/people/", json={}, headers=headers)
        assert rv.status_code == 201
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        assert len(transactions) == 2
        # first
        transaction = transactions[0]
        assert transaction["id"] == 1
        assert transaction["first"] == 1
        assert transaction["last"] == 1
        assert transaction["connection"]["id"] == 1
        assert len(transaction["changes"]) == 1
        change = transaction["changes"][0]
        assert change["obj_class"] == "Person"
        assert change["trans_type"] == 0
        # second
        transaction = transactions[1]
        assert transaction["id"] == 2
        assert transaction["first"] == 1
        assert transaction["last"] == 1
        assert transaction["connection"]["id"] == 2
        assert len(transaction["changes"]) == 1
        change = transaction["changes"][0]
        assert change["obj_class"] == "Person"
        assert change["trans_type"] == 0

    def test_add_modify_delete(self):
        headers = get_headers(self.client, "editor", "123")
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        assert rv.json == []
        rv = self.client.post("/api/people/", json={}, headers=headers)
        assert rv.status_code == 201
        person = rv.json[0]["new"]
        person["gramps_id"] = "new_gramps_id"
        rv = self.client.put(
            f"/api/people/{person['handle']}", json=person, headers=headers
        )
        assert rv.status_code == 200
        rv = self.client.delete(
            f"/api/people/{person['handle']}", json=person, headers=headers
        )
        assert rv.status_code == 200
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        assert len(transactions) == 3
        # first
        transaction = transactions[0]
        assert transaction["id"] == 1
        assert transaction["first"] == 1
        assert transaction["last"] == 1
        assert transaction["connection"]["id"] == 1
        assert len(transaction["changes"]) == 1
        change = transaction["changes"][0]
        assert change["obj_class"] == "Person"
        assert change["trans_type"] == 0
        # second
        transaction = transactions[1]
        assert transaction["id"] == 2
        assert transaction["first"] == 1
        assert transaction["last"] == 1
        assert transaction["connection"]["id"] == 2
        assert len(transaction["changes"]) == 1
        change = transaction["changes"][0]
        assert change["obj_class"] == "Person"
        assert change["trans_type"] == 1
        # third
        transaction = transactions[2]
        assert transaction["id"] == 3
        assert transaction["first"] == 1
        assert transaction["last"] == 1
        assert transaction["connection"]["id"] == 3
        assert len(transaction["changes"]) == 1
        change = transaction["changes"][0]
        assert change["obj_class"] == "Person"
        assert change["trans_type"] == 2
        # keys
        for transaction in transactions:
            assert "old_data" not in transaction["changes"][0]
            assert "new_data" not in transaction["changes"][0]
        rv = self.client.get("/api/transactions/history/?old=1", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        for transaction in transactions:
            assert "old_data" in transaction["changes"][0]
            assert "new_data" not in transaction["changes"][0]
        rv = self.client.get("/api/transactions/history/?old=1&new=1", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        for transaction in transactions:
            assert "old_data" in transaction["changes"][0]
            assert "new_data" in transaction["changes"][0]
        rv = self.client.get(
            "/api/transactions/history/?page=1&pagesize=1", headers=headers
        )
        assert rv.status_code == 200
        transactions = rv.json
        assert len(transactions) == 1
        rv = self.client.get(
            "/api/transactions/history/?page=4&pagesize=1", headers=headers
        )
        assert rv.status_code == 200
        transactions = rv.json
        assert len(transactions) == 0
        rv = self.client.get("/api/transactions/history/?sort=-id", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        assert [t["id"] for t in transactions] == [3, 2, 1]
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        assert len(transactions) == 3
        after = transactions[0]["timestamp"]
        rv = self.client.get(
            f"/api/transactions/history/?after={after}", headers=headers
        )
        assert rv.status_code == 200
        assert len(rv.json) == 2
        before = transactions[1]["timestamp"]
        rv = self.client.get(
            f"/api/transactions/history/?after={before}", headers=headers
        )
        assert rv.status_code == 200
        assert len(rv.json) == 1

    def test_guest(self):
        headers = get_headers(self.client, "user", "123")
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 403

    def test_member(self):
        headers = get_headers(self.client, "member", "123")
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
