#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2023-2026      David Straub
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

"""Tests for the /api/tasks endpoint."""

import os
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import TaskTree, User, add_user, user_db
from gramps_webapi.auth.const import (
    ROLE_GUEST,
    ROLE_MEMBER,
    ROLE_OWNER,
)
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG


@pytest.mark.usefixtures("celery_session_app")
@pytest.mark.usefixtures("celery_session_worker")
class TestTask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API"
        cls.dbman = CLIDbManager(DbState())
        dirpath, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        tree = os.path.basename(dirpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(
                config={
                    "TESTING": True,
                    "RATELIMIT_ENABLED": False,
                    "CELERY_CONFIG": {
                        "broker_url": "redis://",
                        "result_backend": "redis://",
                    },
                }
            )
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="user", password="123", role=ROLE_GUEST, tree=tree)

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_task_noauth(self):
        rv = self.client.get("/api/tasks/nope")
        assert rv.status_code == 401

    def test_task_nonexistant(self):
        rv = self.client.post(
            "/api/token/", json={"username": "user", "password": "123"}
        )
        token = rv.json["access_token"]
        rv = self.client.get(
            "/api/tasks/nope",
            headers={"Authorization": "Bearer {}".format(token)},
        )
        assert rv.status_code == 200
        assert rv.json["state"] == "PENDING"


def _make_app(name):
    """Create a minimal test app backed by a fresh SQLite Gramps database."""
    dbman = CLIDbManager(DbState())
    dirpath, _ = dbman.create_new_db_cli(name, dbid="sqlite")
    tree = os.path.basename(dirpath)
    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
        app = create_app(config={"TESTING": True, "RATELIMIT_ENABLED": False})
    return app, dbman, tree


class TestTaskRecord(unittest.TestCase):
    """Unit tests for _record_task and _purge_expired_task_rows."""

    @classmethod
    def setUpClass(cls):
        from gramps_webapi.api.tasks import _purge_expired_task_rows, _record_task

        cls._record_task = staticmethod(_record_task)
        cls._purge = staticmethod(_purge_expired_task_rows)
        cls.app, cls.dbman, cls.tree = _make_app("TestTaskRecord")
        with cls.app.app_context():
            user_db.create_all()

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database("TestTaskRecord")

    def _make_mock_task(self, name="gramps_webapi.api.tasks.import_file"):
        t = Mock()
        t.name = name
        return t

    def test_record_task_inserts_row(self):
        task_id = str(uuid.uuid4())
        with self.app.app_context():
            self._record_task(
                task_id,
                self._make_mock_task(),
                {"tree": self.tree, "user_id": "test-user-uuid"},
            )
            row = user_db.session.get(TaskTree, task_id)
        assert row is not None
        assert row.tree == self.tree
        assert row.user_id == "test-user-uuid"
        assert row.name == "gramps_webapi.api.tasks.import_file"
        assert row.created_at is not None

    def test_record_task_missing_tree_and_user(self):
        """Tasks dispatched without tree/user_id (e.g. email tasks) store NULL."""
        task_id = str(uuid.uuid4())
        with self.app.app_context():
            self._record_task(task_id, self._make_mock_task("send_email"), {})
            row = user_db.session.get(TaskTree, task_id)
        assert row is not None
        assert row.tree is None
        assert row.user_id is None

    def test_purge_removes_expired_rows(self):
        task_id = str(uuid.uuid4())
        old_ts = datetime.utcnow() - timedelta(hours=25)
        with self.app.app_context():
            row = TaskTree(
                task_id=task_id,
                tree=self.tree,
                user_id=None,
                name="old_task",
                created_at=old_ts,
            )
            user_db.session.add(row)
            user_db.session.commit()
            self._purge()
            assert user_db.session.get(TaskTree, task_id) is None

    def test_purge_keeps_recent_rows(self):
        task_id = str(uuid.uuid4())
        with self.app.app_context():
            row = TaskTree(
                task_id=task_id, tree=self.tree, user_id=None, name="recent_task"
            )
            user_db.session.add(row)
            user_db.session.commit()
            self._purge()
            assert user_db.session.get(TaskTree, task_id) is not None


class TestTaskEndpoints(unittest.TestCase):
    """API tests for GET /api/tasks/ and extended GET /api/tasks/<id>."""

    OWNER_USER_ID = None  # filled in setUpClass

    @classmethod
    def setUpClass(cls):
        cls.app, cls.dbman, cls.tree = _make_app("TestTaskEndpoints")
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="ep_guest", password="pw", role=ROLE_GUEST, tree=cls.tree)
            add_user(name="ep_member", password="pw", role=ROLE_MEMBER, tree=cls.tree)
            add_user(name="ep_owner", password="pw", role=ROLE_OWNER, tree=cls.tree)
            cls.guest_id = str(
                user_db.session.query(User).filter_by(name="ep_guest").scalar().id
            )
            cls.member_id = str(
                user_db.session.query(User).filter_by(name="ep_member").scalar().id
            )
            cls.owner_id = str(
                user_db.session.query(User).filter_by(name="ep_owner").scalar().id
            )

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database("TestTaskEndpoints")

    def _token(self, role_name):
        rv = self.client.post(
            "/api/token/", json={"username": f"ep_{role_name}", "password": "pw"}
        )
        return rv.json["access_token"]

    def _auth(self, role_name):
        return {"Authorization": f"Bearer {self._token(role_name)}"}

    def _insert_row(self, task_id, name="test_task", user_id=None, tree=None):
        with self.app.app_context():
            row = TaskTree(
                task_id=task_id,
                tree=tree if tree is not None else self.tree,
                user_id=user_id,
                name=name,
            )
            user_db.session.add(row)
            user_db.session.commit()

    # --- GET /api/tasks/ ---

    def test_list_requires_auth(self):
        rv = self.client.get("/api/tasks/")
        assert rv.status_code == 401

    def test_list_guest_sees_only_own_tasks(self):
        task_id = str(uuid.uuid4())
        other_id = str(uuid.uuid4())
        self._insert_row(task_id, user_id=self.guest_id)
        self._insert_row(other_id, user_id=self.owner_id)
        rv = self.client.get("/api/tasks/", headers=self._auth("guest"))
        assert rv.status_code == 200
        returned_ids = [t["task_id"] for t in rv.json]
        assert task_id in returned_ids
        assert other_id not in returned_ids

    def test_list_member_sees_only_own_tasks(self):
        task_id = str(uuid.uuid4())
        other_id = str(uuid.uuid4())
        self._insert_row(task_id, user_id=self.member_id)
        self._insert_row(other_id, user_id=self.owner_id)
        rv = self.client.get("/api/tasks/", headers=self._auth("member"))
        assert rv.status_code == 200
        returned_ids = [t["task_id"] for t in rv.json]
        assert task_id in returned_ids
        assert other_id not in returned_ids

    def test_list_owner_sees_all_tasks(self):
        task_id = str(uuid.uuid4())
        other_id = str(uuid.uuid4())
        self._insert_row(task_id, user_id=self.member_id)
        self._insert_row(other_id, user_id=self.owner_id)
        rv = self.client.get("/api/tasks/", headers=self._auth("owner"))
        assert rv.status_code == 200
        returned_ids = [t["task_id"] for t in rv.json]
        assert task_id in returned_ids
        assert other_id in returned_ids

    def test_list_returns_expected_fields(self):
        task_id = str(uuid.uuid4())
        self._insert_row(task_id, name="import_file", user_id=self.owner_id)
        rv = self.client.get("/api/tasks/", headers=self._auth("owner"))
        assert rv.status_code == 200
        task = next((t for t in rv.json if t["task_id"] == task_id), None)
        assert task is not None
        assert task["name"] == "import_file"
        assert task["user_id"] == self.owner_id
        assert task["created_at"] is not None
        assert "state" in task

    def test_list_task_state_pending_without_redis(self):
        """Tasks with a DB row but no Redis result show state PENDING."""
        task_id = str(uuid.uuid4())
        self._insert_row(task_id, user_id=self.owner_id)
        rv = self.client.get("/api/tasks/", headers=self._auth("owner"))
        task = next((t for t in rv.json if t["task_id"] == task_id), None)
        assert task is not None
        assert task["state"] == "PENDING"

    def test_list_sorted_newest_first(self):
        ids = [str(uuid.uuid4()) for _ in range(3)]
        base = datetime.utcnow() - timedelta(hours=3)
        with self.app.app_context():
            for i, tid in enumerate(ids):
                row = TaskTree(
                    task_id=tid,
                    tree=self.tree,
                    user_id=self.owner_id,
                    name="task",
                    created_at=base + timedelta(hours=i),
                )
                user_db.session.add(row)
            user_db.session.commit()
        rv = self.client.get("/api/tasks/", headers=self._auth("owner"))
        returned_ids = [t["task_id"] for t in rv.json if t["task_id"] in ids]
        assert returned_ids == list(reversed(ids))

    # --- GET /api/tasks/<task_id> extended ---

    def test_get_task_no_auth(self):
        rv = self.client.get("/api/tasks/any-id")
        assert rv.status_code == 401

    def test_get_task_without_db_row_returns_pending(self):
        """Unknown task ID: existing fields present, new metadata fields absent."""
        rv = self.client.get("/api/tasks/no-such-id", headers=self._auth("member"))
        assert rv.status_code == 200
        assert rv.json["state"] == "PENDING"
        assert rv.json.get("name") is None
        assert rv.json.get("created_at") is None

    def test_get_task_with_db_row_returns_metadata(self):
        """Task with a DB row: all metadata fields present alongside state."""
        task_id = str(uuid.uuid4())
        self._insert_row(task_id, name="export_db", user_id=self.owner_id)
        rv = self.client.get(f"/api/tasks/{task_id}", headers=self._auth("member"))
        assert rv.status_code == 200
        assert rv.json["task_id"] == task_id
        assert rv.json["name"] == "export_db"
        assert rv.json["user_id"] == self.owner_id
        assert rv.json["created_at"] is not None
        # legacy fields still present
        assert "state" in rv.json
        assert "result" in rv.json

    def test_get_task_with_db_row_state_pending_without_redis(self):
        """DB row present but no Redis entry: state is PENDING."""
        task_id = str(uuid.uuid4())
        self._insert_row(task_id, user_id=self.owner_id)
        rv = self.client.get(f"/api/tasks/{task_id}", headers=self._auth("member"))
        assert rv.status_code == 200
        assert rv.json["state"] == "PENDING"
        assert rv.json["task_id"] == task_id
