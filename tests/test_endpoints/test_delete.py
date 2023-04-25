#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2021      David Straub
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

"""Tests object deletion."""

import os
import unittest
import uuid
from typing import Dict
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import user_db, add_user
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


class TestObjectDeletion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API"
        cls.dbman = CLIDbManager(DbState())
        dirpath, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        tree = os.path.basename(dirpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="user", password="123", role=ROLE_GUEST, tree=tree)
            add_user(
                name="contributor", password="123", role=ROLE_CONTRIBUTOR, tree=tree
            )
            add_user(name="admin", password="123", role=ROLE_OWNER, tree=tree)
            add_user(name="editor", password="123", role=ROLE_EDITOR, tree=tree)
            add_user(name="member", password="123", role=ROLE_MEMBER, tree=tree)

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_delete_permissions(self):
        """Test deletion permissions."""
        handle = make_handle()
        obj = [
            {
                "_class": "Note",
                "handle": handle,
                "text": {"_class": "StyledText", "string": "My first note."},
            }
        ]
        headers_guest = get_headers(self.client, "user", "123")
        headers_contributor = get_headers(self.client, "contributor", "123")
        headers_admin = get_headers(self.client, "admin", "123")
        headers_editor = get_headers(self.client, "editor", "123")
        headers_member = get_headers(self.client, "member", "123")
        # create object as contributor
        rv = self.client.post("/api/objects/", json=obj, headers=headers_contributor)
        self.assertEqual(rv.status_code, 201)
        # try deleting as guest
        rv = self.client.delete(f"/api/notes/{handle}", headers=headers_guest)
        self.assertEqual(rv.status_code, 403)
        # check it's still there
        rv = self.client.get(f"/api/notes/{handle}", headers=headers_guest)
        self.assertEqual(rv.status_code, 200)
        # try deleting as member
        rv = self.client.delete(f"/api/notes/{handle}", headers=headers_member)
        self.assertEqual(rv.status_code, 403)
        # check it's still there
        rv = self.client.get(f"/api/notes/{handle}", headers=headers_guest)
        self.assertEqual(rv.status_code, 200)
        # try deleting as contributor
        rv = self.client.delete(f"/api/notes/{handle}", headers=headers_contributor)
        self.assertEqual(rv.status_code, 403)
        # check it's still there
        rv = self.client.get(f"/api/notes/{handle}", headers=headers_guest)
        self.assertEqual(rv.status_code, 200)
        # try deleting as editor
        rv = self.client.delete(f"/api/notes/{handle}", headers=headers_editor)
        self.assertEqual(rv.status_code, 200)
        # check it's gone
        rv = self.client.get(f"/api/notes/{handle}", headers=headers_guest)
        self.assertEqual(rv.status_code, 404)
        # create again
        rv = self.client.post("/api/objects/", json=obj, headers=headers_contributor)
        # try deleting as admin
        rv = self.client.delete(f"/api/notes/{handle}", headers=headers_admin)
        self.assertEqual(rv.status_code, 200)
        out = rv.json
        # check it's gone
        rv = self.client.get(f"/api/notes/{handle}", headers=headers_guest)
        self.assertEqual(rv.status_code, 404)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["_class"], "Note")
        self.assertEqual(out[0]["handle"], handle)
        self.assertEqual(out[0]["new"], None)
        self.assertEqual(out[0]["old"]["_class"], "Note")
        self.assertEqual(out[0]["type"], "delete")

    def test_delete_right_etag(self):
        handle = make_handle()
        obj = {
            "handle": handle,
            "text": {"_class": "StyledText", "string": "My first note."},
        }

        headers_admin = get_headers(self.client, "admin", "123")
        rv = self.client.post("/api/notes/", json=obj, headers=headers_admin)
        self.assertEqual(rv.status_code, 201)
        rv = self.client.get(f"/api/notes/{handle}", headers=headers_admin)
        self.assertEqual(rv.status_code, 200)
        etag = rv.headers["ETag"]
        rv = self.client.delete(
            f"/api/notes/{handle}",
            headers={**headers_admin, "If-Match": etag},
        )
        self.assertEqual(rv.status_code, 200)
        # check it is gone
        rv = self.client.get(f"/api/notes/{handle}", headers=headers_admin)
        self.assertEqual(rv.status_code, 404)

    def test_delete_wrong_etag(self):
        handle = make_handle()
        obj = {
            "handle": handle,
            "text": {"_class": "StyledText", "string": "My first note."},
        }
        obj_new = {
            "handle": handle,
            "text": {"_class": "StyledText", "string": "My updated note."},
        }
        headers_admin = get_headers(self.client, "admin", "123")
        # POST
        rv = self.client.post("/api/notes/", json=obj, headers=headers_admin)
        self.assertEqual(rv.status_code, 201)
        # GET
        rv = self.client.get(f"/api/notes/{handle}", headers=headers_admin)
        self.assertEqual(rv.status_code, 200)
        etag = rv.headers["ETag"]
        # PUT
        rv = self.client.put(
            f"/api/notes/{handle}", json=obj_new, headers=headers_admin
        )
        self.assertEqual(rv.status_code, 200)
        # DELETE
        rv = self.client.delete(
            f"/api/notes/{handle}",
            headers={**headers_admin, "If-Match": etag},
        )
        # fails!
        self.assertEqual(rv.status_code, 412)
        # check it is still there
        rv = self.client.get(f"/api/notes/{handle}", headers=headers_admin)
        self.assertEqual(rv.status_code, 200)

    def test_search_delete_note(self):
        """Test whether deleting a note updates the search index correctly."""
        handle = make_handle()
        text = make_handle()
        headers = get_headers(self.client, "admin", "123")
        obj = {
            "_class": "Note",
            "handle": handle,
            "text": {"_class": "StyledText", "string": f"Original note: {text}."},
        }
        # create object
        rv = self.client.post("/api/notes/", json=obj, headers=headers)
        self.assertEqual(rv.status_code, 201)
        # find it
        rv = self.client.get(f"/api/search/?query=handle:{handle}", headers=headers)
        self.assertEqual(len(rv.json), 1)
        self.assertEqual(rv.json[0]["handle"], handle)
        # or its text
        rv = self.client.get(f"/api/search/?query={text}", headers=headers)
        self.assertEqual(len(rv.json), 1)
        self.assertEqual(rv.json[0]["handle"], handle)
        # now delete
        rv = self.client.delete(f"/api/notes/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        # don't find it anymore
        rv = self.client.get(f"/api/search/?query=handle:{handle}", headers=headers)
        self.assertEqual(len(rv.json), 0)
        # or its text
        rv = self.client.get(f"/api/search/?query={text}", headers=headers)
        self.assertEqual(len(rv.json), 0)
