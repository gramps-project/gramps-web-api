#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2023      David Straub
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

"""Tests transaction endpoint."""

import os
import unittest
import uuid
from copy import deepcopy
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
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG


def get_headers(client, user: str, password: str) -> Dict[str, str]:
    """Get the auth headers for a specific user."""
    rv = client.post("/api/token/", json={"username": user, "password": password})
    access_token = rv.json["access_token"]
    return {"Authorization": "Bearer {}".format(access_token)}


def make_handle() -> str:
    """Make a new valid handle."""
    return str(uuid.uuid4())


class TestTransactionResource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API"
        cls.dbman = CLIDbManager(DbState())
        dirpath, _ = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        tree = os.path.basename(dirpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="user", password="123", role=ROLE_GUEST, tree=tree)
            add_user(name="admin", password="123", role=ROLE_OWNER, tree=tree)
            add_user(name="member", password="123", role=ROLE_MEMBER, tree=tree)
            add_user(name="editor", password="123", role=ROLE_EDITOR, tree=tree)
            add_user(
                name="contributor", password="123", role=ROLE_CONTRIBUTOR, tree=tree
            )

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_transaction_add_update_delete(self):
        """Add, update, and delete a single note."""
        handle = make_handle()
        obj = {
            "_class": "Note",
            "handle": handle,
            "text": {"_class": "StyledText", "string": "My first note."},
            "gramps_id": "N1",
        }
        trans = [
            {"type": "add", "_class": "Note", "handle": handle, "old": None, "new": obj}
        ]
        for username in ["user", "member", "contributor"]:
            # these three roles should not be able to post a transaction!
            headers = get_headers(self.client, username, "123")
            rv = self.client.post(
                "/api/transactions/?background=1", json=obj, headers=headers
            )
            self.assertEqual(rv.status_code, 403)
        headers = get_headers(self.client, "editor", "123")
        # add
        rv = self.client.post(
            "/api/transactions/?background=1", json=trans, headers=headers
        )
        self.assertEqual(rv.status_code, 200)
        trans_dict = rv.json
        self.assertEqual(len(trans_dict), 1)
        self.assertEqual(trans_dict[0]["handle"], handle)
        self.assertEqual(trans_dict[0]["type"], "add")
        self.assertEqual(trans_dict[0]["_class"], "Note")
        rv = self.client.get(f"/api/notes/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        obj_dict = rv.json
        self.assertEqual(obj_dict["handle"], handle)
        self.assertEqual(obj_dict["text"]["string"], "My first note.")
        # undo add
        rv = self.client.post(
            "/api/transactions/?undo=1&background=1", json=trans_dict, headers=headers
        )
        assert rv.status_code == 200
        trans_dict = rv.json
        self.assertEqual(len(trans_dict), 1)
        self.assertEqual(trans_dict[0]["handle"], handle)
        self.assertEqual(trans_dict[0]["type"], "delete")
        self.assertEqual(trans_dict[0]["_class"], "Note")
        rv = self.client.get(f"/api/notes/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 404)
        # undo undo
        rv = self.client.post(
            "/api/transactions/?undo=1&background=1", json=trans_dict, headers=headers
        )
        assert rv.status_code == 200
        rv = self.client.get(f"/api/notes/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        # update
        obj_new = deepcopy(obj)
        obj_new["gramps_id"] = "N2"
        trans = [
            {
                "type": "update",
                "_class": "Note",
                "handle": handle,
                "old": obj,
                "new": obj_new,
            }
        ]
        rv = self.client.post(
            "/api/transactions/?background=1", json=trans, headers=headers
        )
        self.assertEqual(rv.status_code, 200)
        trans_dict = rv.json
        rv = self.client.get(f"/api/notes/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        obj_dict = rv.json
        self.assertEqual(obj_dict["handle"], handle)
        self.assertEqual(obj_dict["gramps_id"], "N2")
        # undo update
        rv = self.client.post(
            "/api/transactions/?undo=1&background=1", json=trans_dict, headers=headers
        )
        assert rv.status_code == 200
        trans_dict = rv.json
        rv = self.client.get(f"/api/notes/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        obj_dict = rv.json
        self.assertEqual(obj_dict["handle"], handle)
        self.assertEqual(obj_dict["gramps_id"], "N1")
        # undo undo
        rv = self.client.post(
            "/api/transactions/?undo=1&background=1", json=trans_dict, headers=headers
        )
        # delete
        trans = [
            {
                "type": "delete",
                "_class": "Note",
                "handle": handle,
                "old": obj_new,
                "new": None,
            }
        ]
        rv = self.client.post(
            "/api/transactions/?background=1", json=trans, headers=headers
        )
        self.assertEqual(rv.status_code, 200)
        trans_dict = rv.json
        rv = self.client.get(f"/api/notes/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 404)
        # undo delete
        rv = self.client.post(
            "/api/transactions/?undo=1&background=1", json=trans_dict, headers=headers
        )
        self.assertEqual(rv.status_code, 200)
        trans_dict = rv.json
        rv = self.client.get(f"/api/notes/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        # undo undo
        rv = self.client.post(
            "/api/transactions/?undo=1&background=1", json=trans_dict, headers=headers
        )

    def test_family_undo(self):
        """Undo update and subequent deletion of a single note."""
        father = {
            "_class": "Person",
            "handle": make_handle(),
            "gramps_id": "P1",
        }
        mother = {
            "_class": "Person",
            "handle": make_handle(),
            "gramps_id": "P2",
        }
        family = {
            "_class": "Family",
            "handle": make_handle(),
            "gramps_id": "F1",
            "father_handle": father["handle"],
            "mother_handle": mother["handle"],
        }
        headers = get_headers(self.client, "editor", "123")
        # add objects
        rv = self.client.post("/api/people/", json=father, headers=headers)
        assert rv.status_code == 201
        rv = self.client.post("/api/people/", json=mother, headers=headers)
        assert rv.status_code == 201
        rv = self.client.post("/api/families/", json=family, headers=headers)
        assert rv.status_code == 201
        trans_dict = rv.json
        rv = self.client.get(f"/api/people/{father['handle']}", headers=headers)
        assert rv.status_code == 200
        assert rv.json["family_list"] == [family["handle"]]
        rv = self.client.get(f"/api/people/{mother['handle']}", headers=headers)
        assert rv.status_code == 200
        assert rv.json["family_list"] == [family["handle"]]
        rv = self.client.get(f"/api/families/{family['handle']}", headers=headers)
        assert rv.status_code == 200
        # undo family post should delete the family and update the people
        rv = self.client.post(
            "/api/transactions/?undo=1&background=1", json=trans_dict, headers=headers
        )
        rv = self.client.get(f"/api/people/{father['handle']}", headers=headers)
        assert rv.status_code == 200
        assert rv.json["family_list"] == []
        rv = self.client.get(f"/api/people/{mother['handle']}", headers=headers)
        assert rv.status_code == 200
        assert rv.json["family_list"] == []
        rv = self.client.get(f"/api/families/{family['handle']}", headers=headers)
        assert rv.status_code == 404

    def test_modify_two(self):
        """Modify two objects simultaneously."""
        handle1 = make_handle()
        handle2 = make_handle()
        obj1 = {
            "_class": "Note",
            "handle": handle1,
            "text": {"_class": "StyledText", "string": "Note 1."},
            "gramps_id": "N21",
        }
        obj2 = {
            "_class": "Note",
            "handle": handle2,
            "text": {"_class": "StyledText", "string": "Note 2."},
            "gramps_id": "N22",
        }
        obj1_upd = {
            "_class": "Note",
            "handle": handle1,
            "text": {"_class": "StyledText", "string": "Updated note 1."},
            "gramps_id": "N21",
        }
        obj2_upd = {
            "_class": "Note",
            "handle": handle2,
            "text": {"_class": "StyledText", "string": "Updated note 2."},
            "gramps_id": "N22",
        }
        headers = get_headers(self.client, "editor", "123")
        # add
        trans = [
            {
                "type": "add",
                "handle": handle1,
                "_class": "Note",
                "old": None,
                "new": obj1,
            },
            {
                "type": "add",
                "handle": handle2,
                "_class": "Note",
                "old": None,
                "new": obj2,
            },
        ]
        rv = self.client.post(
            "/api/transactions/?background=1", json=trans, headers=headers
        )
        self.assertEqual(rv.status_code, 200)
        trans_dict = rv.json
        self.assertEqual(len(trans_dict), 2)
        self.assertEqual(trans_dict[0]["handle"], handle1)
        self.assertEqual(trans_dict[1]["handle"], handle2)
        rv = self.client.get(f"/api/notes/{handle1}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        obj_dict = rv.json
        self.assertEqual(obj_dict["text"]["string"], "Note 1.")
        rv = self.client.get(f"/api/notes/{handle2}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        obj_dict = rv.json
        self.assertEqual(obj_dict["text"]["string"], "Note 2.")
        # update
        trans = [
            {
                "type": "add",
                "handle": handle1,
                "_class": "Note",
                "old": obj1,
                "new": obj1_upd,
            },
            {
                "type": "add",
                "handle": handle2,
                "_class": "Note",
                "old": obj2,
                "new": obj2_upd,
            },
        ]
        rv = self.client.post(
            "/api/transactions/?background=1", json=trans, headers=headers
        )
        self.assertEqual(rv.status_code, 200)
        rv = self.client.get(f"/api/notes/{handle1}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        obj_dict = rv.json
        self.assertEqual(obj_dict["text"]["string"], "Updated note 1.")
        rv = self.client.get(f"/api/notes/{handle2}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        obj_dict = rv.json
        self.assertEqual(obj_dict["text"]["string"], "Updated note 2.")
        # delete
        trans = [
            {
                "type": "delete",
                "handle": handle1,
                "_class": "Note",
                "old": obj1_upd,
                "new": None,
            },
            {
                "type": "delete",
                "handle": handle2,
                "_class": "Note",
                "old": obj2_upd,
                "new": None,
            },
        ]
        rv = self.client.post(
            "/api/transactions/?background=1", json=trans, headers=headers
        )
        self.assertEqual(rv.status_code, 200)
        rv = self.client.get(f"/api/notes/{handle1}", headers=headers)
        self.assertEqual(rv.status_code, 404)
        rv = self.client.get(f"/api/notes/{handle2}", headers=headers)
        self.assertEqual(rv.status_code, 404)

    def test_missing_handle(self):
        """Add with missing handle."""
        handle = make_handle()
        obj = {
            "_class": "Note",
            "text": {"_class": "StyledText", "string": "My first note."},
            "gramps_id": "N31",
        }
        trans = [{"type": "add", "_class": "Note", "old": None, "new": obj}]
        headers = get_headers(self.client, "editor", "123")
        # add
        rv = self.client.post(
            "/api/transactions/?background=1", json=trans, headers=headers
        )
        self.assertEqual(rv.status_code, 500)

    def test_missing_gramps_id(self):
        """Add with missing gramps ID."""
        handle = make_handle()
        obj = {
            "_class": "Note",
            "text": {"_class": "StyledText", "string": "My first note."},
            "handle": handle,
        }
        trans = [
            {"type": "add", "_class": "Note", "handle": handle, "old": None, "new": obj}
        ]
        headers = get_headers(self.client, "editor", "123")
        # add
        rv = self.client.post(
            "/api/transactions/?background=1", json=trans, headers=headers
        )
        self.assertEqual(rv.status_code, 500)

    def test_gramps60_issue(self):
        """Test for an issue that occurred after upgrading to Gramps 6.0"""
        obj_dict = {
            "handle": "fe171ce847937f3212613fb24c1",
            "change": 1746095141,
            "private": False,
            "tag_list": [],
            "gramps_id": "E4403",
            "citation_list": [],
            "note_list": [],
            "media_list": [],
            "attribute_list": [],
            "date": {
                "format": None,
                "calendar": 0,
                "modifier": 0,
                "quality": 0,
                "dateval": [2, 2, 1991, False],
                "text": "1991-02-02",
                "sortval": 2448290,
                "newyear": 0,
                "_class": "Date",
            },
            "place": "",
            "place_name": "",
            "_class": "Event",
            "type": {"_class": "EventType", "value": 11, "string": ""},
            "description": "Testereignis",
        }
        trans = [
            {
                "type": "add",
                "_class": "Event",
                "handle": obj_dict["handle"],
                "old": None,
                "new": obj_dict,
            }
        ]
        headers = get_headers(self.client, "editor", "123")
        # add
        rv = self.client.post("/api/transactions/", json=trans, headers=headers)
        assert rv.status_code == 200
        rv = self.client.get(f"/api/events/{obj_dict['handle']}", headers=headers)
        assert rv.status_code == 200
        assert rv.json["type"] == "Adopted"
