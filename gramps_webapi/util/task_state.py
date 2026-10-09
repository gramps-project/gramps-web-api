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

"""Task lifecycle and per-tree task locks, tracked in the user database.

The task_tree row is the source of truth for a task's state; the broker only
carries messages.

A task declared with a lock key is exclusive per tree and key. A second
dispatch is rejected (409) or, for a coalescing key, folded into the active
task, which then runs once more. A background thread keeps the heartbeat of
a running task; the reaper marks tasks without heartbeat as lost, releasing
their lock, and tree-writing tasks check that they still hold it right before
writing, so a reaped task never runs concurrently with the next holder.

All writes go through their own connection rather than the session, so they
never commit the caller's pending changes and work from any thread.
"""

from __future__ import annotations

import json
import logging
import threading
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import sqlalchemy as sa
from flask import current_app
from gramps.gen.lib.json_utils import object_to_string
from werkzeug.exceptions import HTTPException

from ..auth import TaskTree, user_db

logger = logging.getLogger(__name__)

# Lock keys. A task dispatched with a key is exclusive per tree and key.
# Rejecting keys answer a second dispatch with 409; coalescing keys fold it
# into the active task, which then runs once more.
LOCK_WRITE = "write"
LOCK_SEARCH_INDEX = "search-index"
LOCK_SEMANTIC_INDEX = "semantic-index"
LOCK_SEARCH_INDEX_INCREMENTAL = "search-index-incremental"
LOCK_SEMANTIC_INDEX_INCREMENTAL = "semantic-index-incremental"
LOCK_MEDIA_USAGE = "media-usage"
COALESCING_LOCKS = frozenset(
    {
        LOCK_SEARCH_INDEX_INCREMENTAL,
        LOCK_SEMANTIC_INDEX_INCREMENTAL,
        LOCK_MEDIA_USAGE,
    }
)

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
LOST = "lost"
UNKNOWN = "unknown"
ACTIVE = (QUEUED, RUNNING)

LOST_MESSAGE = "The task stopped responding and was abandoned"

_table = TaskTree.__table__
_current_task_id: ContextVar[str | None] = ContextVar("current_task_id", default=None)


class TaskLocked(Exception):
    """Another active task on the tree holds a rejecting lock."""

    def __init__(self, holder_id: str):
        super().__init__(holder_id)
        self.holder_id = holder_id


class TaskLockLost(Exception):
    """The task's row is no longer running, so it must not write."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _dump(value: Any) -> str | None:
    """Serialize a result or progress dict, including Gramps objects."""
    if value is None:
        return None
    try:
        return object_to_string(value)
    except TypeError:
        return json.dumps(str(value))


def error_payload(exc: BaseException) -> Any:
    """Return the API error shape of an exception, or its message."""
    if isinstance(exc, HTTPException):
        return {"error": {"code": exc.code, "message": exc.description}}
    # TaskError carries the payload as its only argument
    if len(exc.args) == 1 and isinstance(exc.args[0], dict) and "error" in exc.args[0]:
        return exc.args[0]
    return str(exc)


def _execute(engine: sa.Engine, statement) -> int:
    """Run a statement in its own transaction and return the row count."""
    with engine.begin() as connection:
        return connection.execute(statement).rowcount


def _update(engine: sa.Engine, *where, **values) -> int:
    return _execute(engine, sa.update(_table).where(*where).values(**values))


def reap(tree: str | None) -> None:
    """Mark the tree's active tasks that stopped responding as lost.

    A running task is stale once its heartbeat is older than
    TASK_HEARTBEAT_TIMEOUT; a queued one once it waited longer than
    TASK_QUEUE_TIMEOUT, e.g. because its message was lost.
    """
    if tree is None:
        return
    now = _now()
    heartbeat_timeout = timedelta(seconds=current_app.config["TASK_HEARTBEAT_TIMEOUT"])
    queue_timeout = timedelta(seconds=current_app.config["TASK_QUEUE_TIMEOUT"])
    _update(
        user_db.engine,
        _table.c.tree == tree,
        sa.or_(
            sa.and_(
                _table.c.status == QUEUED,
                _table.c.created_at < now - queue_timeout,
            ),
            sa.and_(
                _table.c.status == RUNNING,
                _table.c.heartbeat_at < now - heartbeat_timeout,
            ),
        ),
        status=LOST,
        lock_key=None,
        finished_at=now,
        result=_dump(LOST_MESSAGE),
    )


def acquire(
    task_id: str, name: str, tree: str | None, user_id: str | None, lock_key: str | None
) -> str | None:
    """Record a task as queued, taking its lock if it has a key.

    Returns None if the task was recorded and must be dispatched. With a
    coalescing key held by another task, returns that task's ID instead: it
    will run once more, so there is nothing to dispatch. With a rejecting key
    held by another task, raises TaskLocked.
    """
    engine = user_db.engine
    insert = sa.insert(_table).values(
        task_id=task_id,
        tree=tree,
        user_id=user_id,
        name=name,
        created_at=_now(),
        status=QUEUED,
        lock_key=lock_key,
    )
    if lock_key is None:
        _execute(engine, insert)
        return None
    reap(tree)
    # a few attempts, since the holder can finish between two statements
    for _attempt in range(3):
        try:
            _execute(engine, insert)
            return None
        except sa.exc.IntegrityError:
            pass
        with engine.connect() as connection:
            holder = connection.scalar(
                sa.select(_table.c.task_id).where(
                    _table.c.tree == tree, _table.c.lock_key == lock_key
                )
            )
        if holder is None:
            continue
        if lock_key not in COALESCING_LOCKS:
            raise TaskLocked(holder)
        if _update(
            engine,
            _table.c.task_id == holder,
            _table.c.lock_key == lock_key,
            rerun=True,
        ):
            return holder
    raise RuntimeError(f"Could not acquire task lock {lock_key} on tree {tree}")


def mark_failed(task_id: str, error: Any) -> None:
    """Fail a task that never started, e.g. because dispatching it failed."""
    _update(
        user_db.engine,
        _table.c.task_id == task_id,
        _table.c.status.in_(ACTIVE),
        status=FAILED,
        lock_key=None,
        finished_at=_now(),
        result=_dump(error),
    )


class _Heartbeat:
    """Background thread proving that the worker running a task is alive.

    Independent of progress reports, so that long steps without any (such as
    loading a backup) do not make the task look stale.
    """

    def __init__(self, engine: sa.Engine, task_id: str, interval: float):
        self._engine = engine
        self._task_id = task_id
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._beat, name=f"task-heartbeat-{task_id}", daemon=True
        )

    def _beat(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                _update(
                    self._engine,
                    _table.c.task_id == self._task_id,
                    _table.c.status == RUNNING,
                    heartbeat_at=_now(),
                )
            except Exception:
                logger.warning("Task heartbeat failed", exc_info=True)

    def __enter__(self) -> _Heartbeat:
        self._thread.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval)


def _finish(
    engine: sa.Engine, task_id: str, status: str, value: Any, unless_rerun: bool
) -> bool:
    """Move a running task to a terminal state, releasing its lock.

    Returns False if the task is no longer running (it was reaped) or, with
    ``unless_rerun``, if a coalesced dispatch asked it to run once more.
    """
    where = [_table.c.task_id == task_id, _table.c.status == RUNNING]
    if unless_rerun:
        where.append(_table.c.rerun.is_(False))
    return bool(
        _update(
            engine,
            *where,
            status=status,
            lock_key=None,
            finished_at=_now(),
            result=_dump(value),
        )
    )


def run_tracked(task_id: str | None, run: Callable[[], Any]) -> Any:
    """Run a task body under its task_tree row.

    Marks the row running, keeps its heartbeat while the body runs, and stores
    the outcome. A task whose row is no longer queued (it was reaped, or its
    message was delivered twice) does not run at all. A task without a row,
    e.g. one dispatched before tracking existed, runs untracked.
    """
    if task_id is None:
        return run()
    engine = user_db.engine
    with engine.connect() as connection:
        row = connection.execute(
            sa.select(_table.c.status, _table.c.lock_key).where(
                _table.c.task_id == task_id
            )
        ).first()
    if row is None or row.status == UNKNOWN:
        return run()
    now = _now()
    if not _update(
        engine,
        _table.c.task_id == task_id,
        _table.c.status == QUEUED,
        status=RUNNING,
        # anything requested so far is covered, since the body has not run yet
        rerun=False,
        started_at=now,
        heartbeat_at=now,
    ):
        logger.info("Task %s is no longer queued, not running it", task_id)
        return None
    coalescing = row.lock_key in COALESCING_LOCKS
    interval = current_app.config["TASK_HEARTBEAT_TIMEOUT"] / 10
    token = _current_task_id.set(task_id)
    try:
        with _Heartbeat(engine, task_id, interval):
            while True:
                try:
                    result = run()
                except BaseException as exc:
                    try:
                        _finish(engine, task_id, FAILED, error_payload(exc), False)
                    except sa.exc.SQLAlchemyError:
                        # don't hide the task's own error; the row gets reaped
                        logger.warning("Failed to store task failure", exc_info=True)
                    raise
                if _finish(engine, task_id, SUCCEEDED, result, coalescing):
                    return result
                # a coalesced dispatch arrived while running: run once more,
                # unless the task was reaped in the meantime
                if not coalescing or not _update(
                    engine,
                    _table.c.task_id == task_id,
                    _table.c.status == RUNNING,
                    _table.c.rerun.is_(True),
                    rerun=False,
                ):
                    return result
    finally:
        _current_task_id.reset(token)


def progress_reporter() -> Callable[[dict], None]:
    """Return a function storing progress of the current task in its row.

    Create it in the task's own thread; the function can then be called from
    any thread. Outside a tracked task, it does nothing.
    """
    task_id = _current_task_id.get()
    if task_id is None:
        return lambda meta: None
    engine = user_db.engine

    def report(meta: dict) -> None:
        try:
            _update(
                engine,
                _table.c.task_id == task_id,
                _table.c.status == RUNNING,
                result=_dump(meta),
            )
        except sa.exc.SQLAlchemyError:
            logger.warning("Failed to store task progress", exc_info=True)

    return report


def ensure_lock_held() -> None:
    """Raise TaskLockLost if the current task is no longer running.

    Called by tree-writing tasks right before they write: a task reaped while
    still alive must not run concurrently with the next lock holder.
    """
    task_id = _current_task_id.get()
    if task_id is None:
        return
    with user_db.engine.connect() as connection:
        status = connection.scalar(
            sa.select(_table.c.status).where(_table.c.task_id == task_id)
        )
    if status != RUNNING:
        raise TaskLockLost(f"Task {task_id} lost its lock before writing")
