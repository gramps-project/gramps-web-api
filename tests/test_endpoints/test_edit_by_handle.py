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

"""Tests for POST /objects/edit-by-handle/."""

import os
import unittest
import uuid
from typing import Dict
from unittest.mock import MagicMock, patch

from celery.result import AsyncResult
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_CONTRIBUTOR, ROLE_EDITOR, ROLE_GUEST
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG

URL = "/api/objects/edit-by-handle/"


def get_headers(client, user: str, password: str) -> Dict[str, str]:
    """Get the auth headers for a specific user."""
    rv = client.post("/api/token/", json={"username": user, "password": password})
    access_token = rv.json["access_token"]
    return {"Authorization": "Bearer {}".format(access_token)}


def make_id() -> str:
    """Make a unique string usable as Gramps ID or tag name."""
    return uuid.uuid4().hex


class TestEditObjectsByHandle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Edit By Handle"
        cls.dbman = CLIDbManager(DbState())
        dirpath, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        tree = os.path.basename(dirpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="guest_ebh", password="123", role=ROLE_GUEST, tree=tree)
            add_user(
                name="contributor_ebh", password="123", role=ROLE_CONTRIBUTOR, tree=tree
            )
            add_user(name="editor_ebh", password="123", role=ROLE_EDITOR, tree=tree)

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def setUp(self):
        self.headers = get_headers(self.client, "editor_ebh", "123")

    def make_tag(self) -> str:
        rv = self.client.post(
            "/api/tags/", json={"name": make_id()}, headers=self.headers
        )
        assert rv.status_code == 201
        return rv.json[0]["handle"]

    def make_note(self, **kwargs) -> str:
        rv = self.client.post(
            "/api/notes/", json={"_class": "Note", **kwargs}, headers=self.headers
        )
        assert rv.status_code == 201
        return rv.json[0]["handle"]

    def get_note(self, handle: str) -> dict:
        rv = self.client.get(f"/api/notes/{handle}", headers=self.headers)
        assert rv.status_code == 200
        return rv.json

    def test_permissions(self):
        handle = self.make_note()
        body = {
            "namespace": "notes",
            "handles": [handle],
            "operations": [{"op": "set_private", "value": True}],
        }
        headers_contributor = get_headers(self.client, "contributor_ebh", "123")
        rv = self.client.post(URL, json=body, headers=headers_contributor)
        assert rv.status_code == 403
        rv = self.client.post(URL, json=body, headers=self.headers)
        assert rv.status_code == 200
        assert self.get_note(handle)["private"] is True

    def test_add_tag_only_commits_changed(self):
        tag = self.make_tag()
        tagged = self.make_note(tag_list=[tag])
        untagged = self.make_note()
        rv = self.client.post(
            URL,
            json={
                "namespace": "notes",
                "handles": [tagged, untagged],
                "operations": [{"op": "add_tag", "handle": tag}],
            },
            headers=self.headers,
        )
        assert rv.status_code == 200
        assert rv.headers["X-Total-Count"] == "1"
        assert len(rv.json) == 1
        assert rv.json[0]["handle"] == untagged
        assert rv.json[0]["type"] == "update"
        assert self.get_note(tagged)["tag_list"] == [tag]
        assert self.get_note(untagged)["tag_list"] == [tag]

    def test_remove_tag(self):
        tag = self.make_tag()
        other_tag = self.make_tag()
        handle = self.make_note(tag_list=[tag, other_tag])
        rv = self.client.post(
            URL,
            json={
                "namespace": "notes",
                "handles": [handle],
                "operations": [{"op": "remove_tag", "handle": tag}],
            },
            headers=self.headers,
        )
        assert rv.status_code == 200
        assert len(rv.json) == 1
        assert self.get_note(handle)["tag_list"] == [other_tag]

    def test_nothing_to_change(self):
        tag = self.make_tag()
        handle = self.make_note()
        rv = self.client.post(
            URL,
            json={
                "namespace": "notes",
                "handles": [handle, make_id()],
                "operations": [
                    {"op": "remove_tag", "handle": tag},
                    {"op": "set_private", "value": False},
                ],
            },
            headers=self.headers,
        )
        assert rv.status_code == 200
        assert rv.headers["X-Total-Count"] == "0"
        assert rv.json == []

    def test_several_operations_one_transaction(self):
        tag = self.make_tag()
        handles = [self.make_note() for _ in range(3)]
        rv = self.client.get(
            "/api/transactions/history/?pagesize=1", headers=self.headers
        )
        count_before = int(rv.headers["X-Total-Count"])
        rv = self.client.post(
            URL,
            json={
                "namespace": "notes",
                # unknown handles are skipped
                "handles": handles + [make_id()],
                "operations": [
                    {"op": "add_tag", "handle": tag},
                    {"op": "set_private", "value": True},
                ],
            },
            headers=self.headers,
        )
        assert rv.status_code == 200
        assert len(rv.json) == 3
        for handle in handles:
            note = self.get_note(handle)
            assert note["tag_list"] == [tag]
            assert note["private"] is True
        rv = self.client.get(
            "/api/transactions/history/?pagesize=1", headers=self.headers
        )
        assert int(rv.headers["X-Total-Count"]) == count_before + 1

    def test_other_object_types(self):
        tag = self.make_tag()
        rv = self.client.post("/api/people/", json={}, headers=self.headers)
        person = rv.json[0]["handle"]
        rv = self.client.post(
            URL,
            json={
                "namespace": "people",
                "handles": [person],
                "operations": [
                    {"op": "add_tag", "handle": tag},
                    {"op": "set_private", "value": True},
                ],
            },
            headers=self.headers,
        )
        assert rv.status_code == 200
        assert len(rv.json) == 1
        assert rv.json[0]["_class"] == "Person"
        rv = self.client.get(f"/api/people/{person}", headers=self.headers)
        assert rv.json["tag_list"] == [tag]
        assert rv.json["private"] is True

    def test_privacy_updates_search_index(self):
        gramps_id = make_id()
        handle = self.make_note(gramps_id=gramps_id)
        headers_guest = get_headers(self.client, "guest_ebh", "123")
        search = f"/api/search/?query={gramps_id}"
        assert len(self.client.get(search, headers=headers_guest).json) == 1
        rv = self.client.post(
            URL,
            json={
                "namespace": "notes",
                "handles": [handle],
                "operations": [{"op": "set_private", "value": True}],
            },
            headers=self.headers,
        )
        assert rv.status_code == 200
        assert len(self.client.get(search, headers=headers_guest).json) == 0
        assert len(self.client.get(search, headers=self.headers).json) == 1
        rv = self.client.post(
            URL,
            json={
                "namespace": "notes",
                "handles": [handle],
                "operations": [{"op": "set_private", "value": False}],
            },
            headers=self.headers,
        )
        assert rv.status_code == 200
        assert len(self.client.get(search, headers=headers_guest).json) == 1

    def test_args(self):
        handle = self.make_note()
        tag = self.make_tag()
        valid_op = {"op": "set_private", "value": True}
        for body in [
            # missing fields
            {"handles": [handle], "operations": [valid_op]},
            {"namespace": "notes", "operations": [valid_op]},
            {"namespace": "notes", "handles": [handle]},
            # empty lists
            {"namespace": "notes", "handles": [], "operations": [valid_op]},
            {"namespace": "notes", "handles": [handle], "operations": []},
            # unknown namespace, and tags cannot be edited
            {"namespace": "cars", "handles": [handle], "operations": [valid_op]},
            {"namespace": "tags", "handles": [tag], "operations": [valid_op]},
            # bad operations
            {"namespace": "notes", "handles": [handle], "operations": [{"op": "x"}]},
            {
                "namespace": "notes",
                "handles": [handle],
                "operations": [{"op": "add_tag"}],
            },
            {
                "namespace": "notes",
                "handles": [handle],
                "operations": [{"op": "set_private"}],
            },
            {
                "namespace": "notes",
                "handles": [handle],
                "operations": [{"op": "set_private", "value": True, "handle": tag}],
            },
            {
                "namespace": "notes",
                "handles": [handle],
                "operations": [{"op": "add_tag", "handle": tag, "value": True}],
            },
        ]:
            rv = self.client.post(URL, json=body, headers=self.headers)
            assert rv.status_code == 422, body

    def test_unknown_tag(self):
        handle = self.make_note()
        rv = self.client.post(
            URL,
            json={
                "namespace": "notes",
                "handles": [handle],
                "operations": [
                    {"op": "set_private", "value": True},
                    {"op": "add_tag", "handle": make_id()},
                ],
            },
            headers=self.headers,
        )
        assert rv.status_code == 422
        # nothing was written
        note = self.get_note(handle)
        assert note["private"] is False
        assert note["tag_list"] == []

    def test_background_without_celery(self):
        """Without a task queue, the edit runs right away and returns the
        transaction like the synchronous path."""
        gramps_id = make_id()
        handle = self.make_note(gramps_id=gramps_id)
        rv = self.client.post(
            URL + "?background=1",
            json={
                "namespace": "notes",
                "handles": [handle],
                "operations": [{"op": "set_private", "value": True}],
            },
            headers=self.headers,
        )
        assert rv.status_code == 200
        assert rv.headers["X-Total-Count"] == "1"
        assert rv.json[0]["handle"] == handle
        assert self.get_note(handle)["private"] is True
        headers_guest = get_headers(self.client, "guest_ebh", "123")
        rv = self.client.get(f"/api/search/?query={gramps_id}", headers=headers_guest)
        assert len(rv.json) == 0

    def test_background_returns_task(self):
        """With a task queue, the background edit returns a task reference."""
        operations = [{"op": "set_private", "value": True}]
        mock_task = MagicMock(spec=AsyncResult)
        mock_task.id = "fake-task-id-789"
        with patch(
            "gramps_webapi.api.resources.objects.run_task",
            return_value=mock_task,
        ) as mock_run_task:
            rv = self.client.post(
                URL + "?background=1",
                json={
                    "namespace": "notes",
                    "handles": ["h1", "h2"],
                    "operations": operations,
                },
                headers=self.headers,
            )
        assert rv.status_code == 202
        assert rv.json["task"]["id"] == "fake-task-id-789"
        kwargs = mock_run_task.call_args.kwargs
        assert kwargs["namespace"] == "notes"
        assert kwargs["handles"] == ["h1", "h2"]
        assert kwargs["operations"] == operations
