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

"""Tests for the task lifecycle and per-tree task locks."""

import json
import unittest
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from werkzeug.exceptions import HTTPException

from gramps_webapi.app import create_app
from gramps_webapi.auth import TaskTree, user_db
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from gramps_webapi.util.task_state import (
    FAILED,
    LOCK_SEARCH_INDEX_INCREMENTAL,
    LOCK_WRITE,
    LOST,
    QUEUED,
    RUNNING,
    SUCCEEDED,
    TaskLocked,
    TaskLockLost,
    acquire,
    ensure_lock_held,
    progress_reporter,
    reap,
    run_tracked,
)


def _new_id() -> str:
    return str(uuid.uuid4())


class TaskStateTestCase(unittest.TestCase):
    """Runs every test in an app context, on a tree of its own."""

    @classmethod
    def setUpClass(cls):
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(config={"TESTING": True, "RATELIMIT_ENABLED": False})

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()
        user_db.create_all()
        self.tree = f"tree-{_new_id()}"

    def tearDown(self):
        user_db.session.remove()
        self.ctx.pop()

    def _row(self, task_id: str) -> TaskTree:
        user_db.session.expire_all()
        return user_db.session.get(TaskTree, task_id)

    def _acquire(self, lock_key=None, tree=None) -> tuple[str, str | None]:
        task_id = _new_id()
        holder = acquire(task_id, "task", tree or self.tree, "user", lock_key)
        return task_id, holder


class TestAcquire(TaskStateTestCase):
    def test_records_queued_row(self):
        task_id, holder = self._acquire()
        assert holder is None
        row = self._row(task_id)
        assert row.status == QUEUED
        assert row.tree == self.tree
        assert row.user_id == "user"
        assert row.lock_key is None

    def test_unlocked_tasks_never_conflict(self):
        self._acquire()
        _, holder = self._acquire()
        assert holder is None

    def test_rejecting_lock_is_exclusive_per_tree(self):
        first, _ = self._acquire(LOCK_WRITE)
        with pytest.raises(TaskLocked) as info:
            self._acquire(LOCK_WRITE)
        assert info.value.holder_id == first

    def test_other_tree_is_not_locked(self):
        self._acquire(LOCK_WRITE)
        _, holder = self._acquire(LOCK_WRITE, tree=f"other-{_new_id()}")
        assert holder is None

    def test_coalescing_lock_folds_into_holder(self):
        first, _ = self._acquire(LOCK_SEARCH_INDEX_INCREMENTAL)
        second, holder = self._acquire(LOCK_SEARCH_INDEX_INCREMENTAL)
        assert holder == first
        assert self._row(second) is None
        assert self._row(first).rerun

    def test_lock_is_released_when_task_finishes(self):
        first, _ = self._acquire(LOCK_WRITE)
        run_tracked(first, lambda: None)
        _, holder = self._acquire(LOCK_WRITE)
        assert holder is None


class TestRunTracked(TaskStateTestCase):
    def test_success_stores_result(self):
        task_id, _ = self._acquire(LOCK_WRITE)
        assert run_tracked(task_id, lambda: {"people": 3}) == {"people": 3}
        row = self._row(task_id)
        assert row.status == SUCCEEDED
        assert json.loads(row.result) == {"people": 3}
        assert row.lock_key is None
        assert row.started_at is not None
        assert row.finished_at is not None

    def test_failure_stores_api_error(self):
        task_id, _ = self._acquire(LOCK_WRITE)
        exc = HTTPException(description="Not allowed by people quota")
        exc.code = 405

        def fail():
            raise exc

        with pytest.raises(HTTPException):
            run_tracked(task_id, fail)
        row = self._row(task_id)
        assert row.status == FAILED
        assert row.lock_key is None
        assert json.loads(row.result) == {
            "error": {"code": 405, "message": "Not allowed by people quota"}
        }

    def test_task_that_is_no_longer_queued_does_not_run(self):
        task_id, _ = self._acquire(LOCK_WRITE)
        run_tracked(task_id, lambda: None)
        body = MagicMock()
        assert run_tracked(task_id, body) is None
        body.assert_not_called()

    def test_untracked_task_runs(self):
        assert run_tracked(_new_id(), lambda: 42) == 42
        assert run_tracked(None, lambda: 42) == 42

    def test_coalesced_dispatch_during_run_runs_body_again(self):
        task_id, _ = self._acquire(LOCK_SEARCH_INDEX_INCREMENTAL)
        calls = []

        def body():
            calls.append(None)
            if len(calls) == 1:
                # another upload arrives while the reindex is running
                _, holder = self._acquire(LOCK_SEARCH_INDEX_INCREMENTAL)
                assert holder == task_id

        run_tracked(task_id, body)
        assert len(calls) == 2
        row = self._row(task_id)
        assert row.status == SUCCEEDED
        assert not row.rerun
        assert row.lock_key is None

    def test_coalesced_dispatch_before_start_runs_body_once(self):
        task_id, _ = self._acquire(LOCK_SEARCH_INDEX_INCREMENTAL)
        self._acquire(LOCK_SEARCH_INDEX_INCREMENTAL)
        body = MagicMock()
        run_tracked(task_id, body)
        body.assert_called_once()


class TestReap(TaskStateTestCase):
    def _age(self, task_id: str, **columns) -> None:
        user_db.session.query(TaskTree).filter_by(task_id=task_id).update(columns)
        user_db.session.commit()

    def test_running_task_without_heartbeat_is_lost(self):
        task_id, _ = self._acquire(LOCK_WRITE)
        stale = datetime.utcnow() - timedelta(hours=1)
        self._age(task_id, status=RUNNING, started_at=stale, heartbeat_at=stale)
        reap(self.tree)
        row = self._row(task_id)
        assert row.status == LOST
        assert row.lock_key is None
        _, holder = self._acquire(LOCK_WRITE)
        assert holder is None

    def test_running_task_with_recent_heartbeat_is_kept(self):
        task_id, _ = self._acquire(LOCK_WRITE)
        self._age(task_id, status=RUNNING, heartbeat_at=datetime.utcnow())
        reap(self.tree)
        assert self._row(task_id).status == RUNNING

    def test_queued_task_waits_for_queue_timeout(self):
        task_id, _ = self._acquire(LOCK_WRITE)
        self._age(task_id, created_at=datetime.utcnow() - timedelta(hours=1))
        reap(self.tree)
        assert self._row(task_id).status == QUEUED
        self._age(task_id, created_at=datetime.utcnow() - timedelta(days=1))
        reap(self.tree)
        assert self._row(task_id).status == LOST

    def test_acquire_reaps_stale_holder(self):
        task_id, _ = self._acquire(LOCK_WRITE)
        stale = datetime.utcnow() - timedelta(hours=1)
        self._age(task_id, status=RUNNING, heartbeat_at=stale)
        _, holder = self._acquire(LOCK_WRITE)
        assert holder is None
        assert self._row(task_id).status == LOST

    def test_reaped_task_must_not_write(self):
        task_id, _ = self._acquire(LOCK_WRITE)

        def body():
            ensure_lock_held()
            self._age(task_id, status=LOST, lock_key=None)
            ensure_lock_held()

        with pytest.raises(TaskLockLost):
            run_tracked(task_id, body)
        # the reaper's verdict stands
        assert self._row(task_id).status == LOST


class TestProgress(TaskStateTestCase):
    def test_progress_is_stored_while_running(self):
        task_id, _ = self._acquire()
        seen = {}

        def body():
            progress_reporter()({"progress": 0.5})
            seen.update(json.loads(self._row(task_id).result))

        run_tracked(task_id, body)
        assert seen == {"progress": 0.5}

    def test_reporter_outside_task_does_nothing(self):
        progress_reporter()({"progress": 0.5})


class TestRunTaskInline(TaskStateTestCase):
    """Without a task queue, locks apply to tasks run in the request."""

    def test_second_write_is_rejected_with_conflict(self):
        from gramps_webapi.api.tasks import run_task

        holder, _ = self._acquire(LOCK_WRITE)
        task = MagicMock()
        task.name = "restore_backup"
        task.lock_key = LOCK_WRITE
        with self.app.test_request_context():
            with pytest.raises(HTTPException) as info:
                run_task(task, tree=self.tree, user_id="user")
        assert info.value.code == 409
        error = info.value.response.get_json()["error"]
        assert error["task"]["id"] == holder
        task.assert_not_called()

    def test_write_runs_and_releases_lock(self):
        from gramps_webapi.api.tasks import run_task

        task = MagicMock(return_value={"ok": True})
        task.name = "restore_backup"
        task.lock_key = LOCK_WRITE
        with self.app.test_request_context():
            result = run_task(task, tree=self.tree, user_id="user")
        assert result == {"ok": True}
        _, holder = self._acquire(LOCK_WRITE)
        assert holder is None

    def test_dry_run_does_not_lock(self):
        from gramps_webapi.api.tasks import run_task

        self._acquire(LOCK_WRITE)
        task = MagicMock(return_value={"people": 3})
        task.name = "restore_backup"
        task.lock_key = LOCK_WRITE
        with self.app.test_request_context():
            result = run_task(task, tree=self.tree, user_id="user", dry_run=True)
        assert result == {"people": 3}

    def test_tree_writing_tasks_declare_the_write_lock(self):
        from gramps_webapi.api import tasks

        for task in [
            tasks.import_file,
            tasks.restore_backup,
            tasks.delete_objects,
            tasks.check_repair_database,
            tasks.upgrade_database_schema,
            tasks.import_media_archive,
        ]:
            assert task.lock_key == LOCK_WRITE, task.name
        assert getattr(tasks.process_transactions, "lock_key", None) is None
