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

    def test_undo_transaction_add(self):
        """Test undoing a transaction that added a person."""
        headers = get_headers(self.client, "editor", "123")

        # Add a person
        rv = self.client.post("/api/people/", json={}, headers=headers)
        assert rv.status_code == 201
        person = rv.json[0]["new"]
        person_handle = person["handle"]

        # Verify person exists
        rv = self.client.get(f"/api/people/{person_handle}", headers=headers)
        assert rv.status_code == 200

        # Get transaction history
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        assert len(transactions) == 1
        transaction_id = transactions[0]["id"]

        # Undo the transaction
        rv = self.client.post(
            f"/api/transactions/history/{transaction_id}/undo", headers=headers
        )
        assert rv.status_code == 200

        # Verify person no longer exists
        rv = self.client.get(f"/api/people/{person_handle}", headers=headers)
        assert rv.status_code == 404

        # Verify we have two transactions now (add + undo)
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        assert len(transactions) == 2

    def test_undo_transaction_update(self):
        """Test undoing a transaction that updated a person."""
        headers = get_headers(self.client, "editor", "123")

        # Add a person
        rv = self.client.post("/api/people/", json={}, headers=headers)
        assert rv.status_code == 201
        person = rv.json[0]["new"]
        person_handle = person["handle"]
        original_gramps_id = person["gramps_id"]

        # Update the person
        person["gramps_id"] = "UPDATED_ID"
        rv = self.client.put(
            f"/api/people/{person_handle}", json=person, headers=headers
        )
        assert rv.status_code == 200

        # Verify update
        rv = self.client.get(f"/api/people/{person_handle}", headers=headers)
        assert rv.status_code == 200
        updated_person = rv.json
        assert updated_person["gramps_id"] == "UPDATED_ID"

        # Get the update transaction (should be transaction ID 2)
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        assert len(transactions) == 2
        update_transaction_id = transactions[1]["id"]  # Second transaction

        # Undo the update transaction
        rv = self.client.post(
            f"/api/transactions/history/{update_transaction_id}/undo", headers=headers
        )
        assert rv.status_code == 200

        # Verify person has original gramps_id
        rv = self.client.get(f"/api/people/{person_handle}", headers=headers)
        assert rv.status_code == 200
        reverted_person = rv.json
        assert reverted_person["gramps_id"] == original_gramps_id

    def test_undo_transaction_delete(self):
        """Test undoing a transaction that deleted a person."""
        headers = get_headers(self.client, "editor", "123")

        # Add a person
        rv = self.client.post("/api/people/", json={}, headers=headers)
        assert rv.status_code == 201
        person = rv.json[0]["new"]
        person_handle = person["handle"]

        # Delete the person
        rv = self.client.delete(f"/api/people/{person_handle}", headers=headers)
        assert rv.status_code == 200

        # Verify person is deleted
        rv = self.client.get(f"/api/people/{person_handle}", headers=headers)
        assert rv.status_code == 404

        # Get the delete transaction (should be transaction ID 2)
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        assert len(transactions) == 2
        delete_transaction_id = transactions[1]["id"]  # Second transaction

        # Undo the delete transaction (use force=1 since the object was deleted)
        rv = self.client.post(
            f"/api/transactions/history/{delete_transaction_id}/undo?force=1",
            headers=headers,
        )
        assert rv.status_code == 200

        # Verify person exists again
        rv = self.client.get(f"/api/people/{person_handle}", headers=headers)
        assert rv.status_code == 200

    def test_undo_transaction_background(self):
        """Test undoing a transaction (background processing is now default)."""
        headers = get_headers(self.client, "editor", "123")

        # Add a person
        rv = self.client.post("/api/people/", json={}, headers=headers)
        assert rv.status_code == 201
        person = rv.json[0]["new"]
        person_handle = person["handle"]

        # Get transaction history
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        transaction_id = transactions[0]["id"]

        rv = self.client.post(
            f"/api/transactions/history/{transaction_id}/undo",
            headers=headers,
        )
        assert rv.status_code == 200

        # Verify person no longer exists
        rv = self.client.get(f"/api/people/{person_handle}", headers=headers)
        assert rv.status_code == 404

    def test_undo_transaction_not_found(self):
        """Test undoing a non-existent transaction."""
        headers = get_headers(self.client, "editor", "123")

        # Try to undo a non-existent transaction
        rv = self.client.post("/api/transactions/history/999/undo", headers=headers)
        assert rv.status_code == 404

    def test_undo_transaction_permissions(self):
        """Test that only users with proper permissions can undo transactions."""
        headers_editor = get_headers(self.client, "editor", "123")
        headers_guest = get_headers(self.client, "user", "123")

        # Add a person as editor
        rv = self.client.post("/api/people/", json={}, headers=headers_editor)
        assert rv.status_code == 201

        # Get transaction history
        rv = self.client.get("/api/transactions/history/", headers=headers_editor)
        assert rv.status_code == 200
        transactions = rv.json
        transaction_id = transactions[0]["id"]

        # Try to undo as guest (should fail)
        rv = self.client.post(
            f"/api/transactions/history/{transaction_id}/undo", headers=headers_guest
        )
        assert rv.status_code == 403

    def test_undo_endpoint(self):
        """Test that the undo endpoint works correctly."""
        headers = get_headers(self.client, "editor", "123")

        # Add two people
        rv = self.client.post("/api/people/", json={}, headers=headers)
        assert rv.status_code == 201
        person1_handle = rv.json[0]["new"]["handle"]

        rv = self.client.post("/api/people/", json={}, headers=headers)
        assert rv.status_code == 201
        person2_handle = rv.json[0]["new"]["handle"]

        # Get transaction history
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        assert len(transactions) == 2

        # Test the /undo route /transactions/history/{id}/undo
        transaction_id_1 = transactions[0]["id"]
        rv = self.client.post(
            f"/api/transactions/history/{transaction_id_1}/undo", headers=headers
        )
        assert rv.status_code == 200

        # Verify first person is gone
        rv = self.client.get(f"/api/people/{person1_handle}", headers=headers)
        assert rv.status_code == 404

        # Test the /undo route for second transaction
        transaction_id_2 = transactions[1]["id"]
        rv = self.client.post(
            f"/api/transactions/history/{transaction_id_2}/undo", headers=headers
        )
        assert rv.status_code == 200

        # Verify second person is gone
        rv = self.client.get(f"/api/people/{person2_handle}", headers=headers)
        assert rv.status_code == 404

    def test_undo_person_reference(self):
        """Test undoing a transaction that added a person reference between two people."""
        headers = get_headers(self.client, "editor", "123")

        # Add first person
        rv = self.client.post("/api/people/", json={}, headers=headers)
        assert rv.status_code == 201
        person1 = rv.json[0]["new"]
        person1_handle = person1["handle"]

        # Add second person
        rv = self.client.post("/api/people/", json={}, headers=headers)
        assert rv.status_code == 201
        person2 = rv.json[0]["new"]
        person2_handle = person2["handle"]

        # Get person1 data to modify
        rv = self.client.get(f"/api/people/{person1_handle}", headers=headers)
        assert rv.status_code == 200
        person1_data = rv.json

        # Add person reference from person1 to person2
        person1_data["person_ref_list"] = [
            {
                "_class": "PersonRef",
                "ref": person2_handle,
                "rel": "Unknown",
                "private": False,
            }
        ]

        # Update person1 with the person reference
        rv = self.client.put(
            f"/api/people/{person1_handle}", json=person1_data, headers=headers
        )
        assert rv.status_code == 200

        # Verify the person reference was added
        rv = self.client.get(f"/api/people/{person1_handle}", headers=headers)
        assert rv.status_code == 200
        updated_person1 = rv.json
        assert len(updated_person1["person_ref_list"]) == 1
        assert updated_person1["person_ref_list"][0]["ref"] == person2_handle

        # Get transaction history - should have 3 transactions (add person1, add person2, add reference)
        rv = self.client.get("/api/transactions/history/?old=1&new=1", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        assert len(transactions) == 3

        # The reference addition should be the third transaction
        reference_transaction_id = transactions[2]["id"]

        # Undo the person reference transaction
        rv = self.client.post(
            f"/api/transactions/history/{reference_transaction_id}/undo",
            headers=headers,
        )
        if rv.status_code != 200:
            # Try with force if it fails due to object changes
            rv = self.client.post(
                f"/api/transactions/history/{reference_transaction_id}/undo?force=1",
                headers=headers,
            )
        assert rv.status_code == 200

        # Verify the person reference was removed
        rv = self.client.get(f"/api/people/{person1_handle}", headers=headers)
        assert rv.status_code == 200
        reverted_person1 = rv.json
        assert len(reverted_person1["person_ref_list"]) == 0

        # Verify both people still exist
        rv = self.client.get(f"/api/people/{person1_handle}", headers=headers)
        assert rv.status_code == 200
        rv = self.client.get(f"/api/people/{person2_handle}", headers=headers)
        assert rv.status_code == 200

    def test_undo_check_endpoint(self):
        """Test the GET method on undo endpoint to check if transaction can be undone."""
        headers = get_headers(self.client, "editor", "123")

        # Add a person
        rv = self.client.post("/api/people/", json={}, headers=headers)
        assert rv.status_code == 201
        person = rv.json[0]["new"]
        person_handle = person["handle"]

        # Get transaction history
        rv = self.client.get("/api/transactions/history/", headers=headers)
        assert rv.status_code == 200
        transactions = rv.json
        transaction_id = transactions[0]["id"]

        # Check if we can undo the transaction (should be OK since nothing changed)
        rv = self.client.get(
            f"/api/transactions/history/{transaction_id}/undo", headers=headers
        )
        assert rv.status_code == 200
        result = rv.json

        # Should be able to undo without force
        assert result["can_undo_without_force"] is True
        assert result["transaction_id"] == transaction_id
        assert result["conflicts_count"] == 0
        assert result["total_changes"] >= 1  # At least one change (person creation)
        assert isinstance(result["conflicts"], list)

        # Now modify the person to create a conflict
        rv = self.client.get(f"/api/people/{person_handle}", headers=headers)
        assert rv.status_code == 200
        person_data = rv.json
        person_data["gramps_id"] = "I9999"  # Change something

        rv = self.client.put(
            f"/api/people/{person_handle}", json=person_data, headers=headers
        )
        assert rv.status_code == 200

        # Check undo again - should now have conflicts
        rv = self.client.get(
            f"/api/transactions/history/{transaction_id}/undo", headers=headers
        )
        assert rv.status_code == 200
        result = rv.json


        # Should NOT be able to undo without force due to changes
        assert result["can_undo_without_force"] is False
        assert result["conflicts_count"] > 0
        assert len(result["conflicts"]) > 0

        # Check conflict details
        conflict = result["conflicts"][0]
        assert conflict["object_class"] == "Person"
        assert conflict["handle"] == person_handle
        assert conflict["conflict_type"] == "object_changed"
