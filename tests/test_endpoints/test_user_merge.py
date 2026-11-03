#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Gramps Web contributors
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

"""Tests for merging two users."""

import os
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import (
    AccessToken,
    PushSubscription,
    TaskTree,
    UserMergeError,
    add_user,
    create_oidc_account,
    create_user_access_token,
    get_guid,
    get_user_details,
    get_user_oidc_accounts,
    merge_users,
    rotate_user_access_token,
    upsert_user_push_subscription,
    user_db,
)
from gramps_webapi.auth.const import (
    ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS,
    ACCESS_TOKEN_SCOPE_SYNC,
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_MEMBER,
    ROLE_OWNER,
)
from gramps_webapi.const import (
    ENV_CONFIG_FILE,
    TEST_EMPTY_GRAMPS_AUTH_CONFIG,
    TREE_MULTI,
)

from . import BASE_URL, get_test_client


def merge_url(name):
    return f"{BASE_URL}/users/{name}/merge/"


class TestUserMerge(unittest.TestCase):
    """Test cases for /users/<name>/merge/ on a single tree."""

    def setUp(self):
        self.name = f"Test Web API Merge {uuid4().hex[:8]}"
        self.dbman = CLIDbManager(DbState())
        dirpath, _ = self.dbman.create_new_db_cli(self.name, dbid="sqlite")
        self.addCleanup(self.dbman.remove_database, self.name)
        tree = os.path.basename(dirpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EMPTY_GRAMPS_AUTH_CONFIG}):
            self.app = create_app(config_from_env=False, config={"TREE": self.name})
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.app.app_context():
            user_db.create_all()
            add_user(name="admin", password="secret", role=ROLE_ADMIN, tree=tree)
            add_user(name="admin2", password="secret", role=ROLE_ADMIN, tree=tree)
            add_user(name="owner", password="secret", role=ROLE_OWNER, tree=tree)
            add_user(
                name="target",
                password="secret",
                role=ROLE_EDITOR,
                tree=tree,
                email="target@example.com",
            )
            add_user(name="source", password="other", role=ROLE_EDITOR, tree=tree)
            self.target_id = str(get_guid("target"))
            self.source_id = str(get_guid("source"))

    def _header(self, name="admin", password="secret", fresh=True):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": name, "password": password}
        )
        self.assertEqual(rv.status_code, 200)
        if fresh:
            return {"Authorization": f"Bearer {rv.json['access_token']}"}
        rv = self.client.post(
            BASE_URL + "/token/refresh/",
            headers={"Authorization": f"Bearer {rv.json['refresh_token']}"},
        )
        return {"Authorization": f"Bearer {rv.json['access_token']}"}

    def _merge(self, target="target", source="source", **kwargs):
        return self.client.post(
            merge_url(target), json={"source": source}, headers=self._header(**kwargs)
        )

    def _tokens(self, user_id, scope):
        with self.app.app_context():
            return sorted(
                (token.label, token.token_hash is not None)
                for token in user_db.session.query(AccessToken).filter_by(
                    user_id=user_id, scope=scope
                )
            )

    def test_merge_moves_the_sources_data(self):
        with self.app.app_context():
            create_oidc_account(self.source_id, "google", "sub-1", "s@example.com")
            create_oidc_account(self.target_id, "custom", "sub-2")
            upsert_user_push_subscription(
                self.source_id, "https://push.example.com/1", "key", "auth"
            )
            user_db.session.add(
                TaskTree(task_id="task-1", name="export", user_id=self.source_id)
            )
            user_db.session.commit()
        rv = self._merge()
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json["name"], "target")
        self.assertEqual(rv.json["email"], "target@example.com")
        self.assertEqual(rv.json["role"], ROLE_EDITOR)
        self.assertEqual(
            sorted(a["provider_id"] for a in rv.json["oidc_accounts"]),
            ["custom", "google"],
        )
        with self.app.app_context():
            self.assertIsNone(get_user_details("source"))
            self.assertEqual(len(get_user_oidc_accounts(self.target_id)), 2)
            subscription = user_db.session.query(PushSubscription).one()
            self.assertEqual(str(subscription.user_id), self.target_id)
            task = user_db.session.query(TaskTree).filter_by(task_id="task-1").one()
            self.assertEqual(task.user_id, self.target_id)

    def test_the_target_keeps_its_password(self):
        self.assertEqual(self._merge().status_code, 200)
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "target", "password": "secret"}
        )
        self.assertEqual(rv.status_code, 200)
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "source", "password": "other"}
        )
        self.assertEqual(rv.status_code, 403)

    def test_the_sources_sessions_end(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "source", "password": "other"}
        )
        refresh = {"Authorization": f"Bearer {rv.json['refresh_token']}"}
        self.assertEqual(self._merge().status_code, 200)
        rv = self.client.post(BASE_URL + "/token/refresh/", headers=refresh)
        self.assertNotEqual(rv.status_code, 200)

    def test_sync_tokens_with_the_same_label_are_renamed(self):
        with self.app.app_context():
            create_user_access_token("target", ACCESS_TOKEN_SCOPE_SYNC, "laptop")
            create_user_access_token("source", ACCESS_TOKEN_SCOPE_SYNC, "laptop")
            create_user_access_token("source", ACCESS_TOKEN_SCOPE_SYNC, "phone")
        self.assertEqual(self._merge().status_code, 200)
        self.assertEqual(
            self._tokens(self.target_id, ACCESS_TOKEN_SCOPE_SYNC),
            [("laptop", True), ("laptop (2)", True), ("phone", True)],
        )

    def test_a_renamed_label_can_be_one_of_the_sources(self):
        with self.app.app_context():
            create_user_access_token("target", ACCESS_TOKEN_SCOPE_SYNC, "laptop")
            create_user_access_token("source", ACCESS_TOKEN_SCOPE_SYNC, "laptop")
            create_user_access_token("source", ACCESS_TOKEN_SCOPE_SYNC, "laptop (2)")
        self.assertEqual(self._merge().status_code, 200)
        self.assertEqual(
            self._tokens(self.target_id, ACCESS_TOKEN_SCOPE_SYNC),
            [("laptop", True), ("laptop (2)", True), ("laptop (3)", True)],
        )

    def test_a_tree_changed_before_the_lock_is_refused(self):
        with self.app.app_context():
            tree = get_user_details("target")["tree"]
            with self.assertRaises(UserMergeError):
                merge_users(self.source_id, self.target_id, "other", tree)
            with self.assertRaises(UserMergeError):
                merge_users(self.source_id, self.target_id, tree, "other")
            self.assertIsNotNone(get_user_details("source"))

    def test_the_targets_calendar_token_is_kept(self):
        with self.app.app_context():
            kept = rotate_user_access_token(
                "target", ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS
            )
            rotate_user_access_token("source", ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS)
        self.assertEqual(self._merge().status_code, 200)
        rv = self.client.get(f"{BASE_URL}/anniversaries.ics?token={kept}")
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(
            self._tokens(self.target_id, ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS),
            [("", True)],
        )
        self.assertEqual(
            self._tokens(self.source_id, ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS), []
        )

    def test_the_sources_calendar_token_moves_if_the_target_has_none(self):
        with self.app.app_context():
            moved = rotate_user_access_token(
                "source", ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS
            )
        self.assertEqual(self._merge().status_code, 200)
        rv = self.client.get(f"{BASE_URL}/anniversaries.ics?token={moved}")
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(
            self._tokens(self.target_id, ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS),
            [("", True)],
        )

    def test_the_history_shows_the_target(self):
        rv = self.client.post(
            BASE_URL + "/people/",
            json={},
            headers=self._header("source", "other"),
        )
        self.assertEqual(rv.status_code, 201)
        self.assertEqual(self._merge().status_code, 200)
        rv = self.client.get(
            BASE_URL + "/transactions/history/", headers=self._header("target")
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json[0]["connection"]["user"]["name"], "target")

    def test_owners_cannot_merge(self):
        self.assertEqual(self._merge(name="owner").status_code, 403)
        with self.app.app_context():
            self.assertIsNotNone(get_user_details("source"))

    def test_merge_needs_a_fresh_token(self):
        self.assertEqual(self._merge(fresh=False).status_code, 401)
        with self.app.app_context():
            self.assertIsNotNone(get_user_details("source"))

    def test_unknown_users(self):
        self.assertEqual(self._merge(source="nobody").status_code, 404)
        self.assertEqual(self._merge(target="nobody").status_code, 404)

    def test_merging_a_user_into_itself(self):
        self.assertEqual(self._merge(source="target").status_code, 400)

    def test_merging_away_the_own_user(self):
        rv = self._merge(target="admin2", source="admin")
        self.assertEqual(rv.status_code, 409)
        with self.app.app_context():
            self.assertIsNotNone(get_user_details("admin"))

    def test_a_higher_role_is_not_merged_into_a_lower_one(self):
        rv = self._merge(target="target", source="owner")
        self.assertEqual(rv.status_code, 409)
        with self.app.app_context():
            self.assertIsNotNone(get_user_details("owner"))
        rv = self._merge(target="owner", source="target")
        self.assertEqual(rv.status_code, 200)

    def test_the_source_is_required(self):
        rv = self.client.post(merge_url("target"), json={}, headers=self._header())
        self.assertEqual(rv.status_code, 422)


class TestUserMergeTrees(unittest.TestCase):
    """Merging users of different trees."""

    @classmethod
    def setUpClass(cls):
        cls.client = get_test_client()
        cls.app = cls.client.application

    def test_users_of_different_trees_are_not_merged(self):
        rv = self.client.post(
            BASE_URL + "/token/", json={"username": "admin", "password": "ghi"}
        )
        header = {"Authorization": f"Bearer {rv.json['access_token']}"}
        rv = self.client.post(
            merge_url("member"), json={"source": "member_empty"}, headers=header
        )
        self.assertEqual(rv.status_code, 409)
        with self.app.app_context():
            self.assertEqual(get_user_details("member_empty")["role"], ROLE_MEMBER)


class TestConcurrentMerge(unittest.TestCase):
    """Two merges in opposite directions against a SQLite file."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        # a config file left in the environment by another test would be loaded
        with patch.dict(os.environ):
            os.environ.pop(ENV_CONFIG_FILE, None)
            self.app = create_app(
                config={
                    "TREE": TREE_MULTI,
                    "SECRET_KEY": "secret",
                    "USER_DB_URI": "sqlite:///" + os.path.join(self.tmpdir, "u.sqlite"),
                },
                config_from_env=False,
            )
        with self.app.app_context():
            user_db.create_all()
            for name in ("one", "two"):
                add_user(name=name, password="secret", role=ROLE_EDITOR)
            self.ids = [str(get_guid(name)) for name in ("one", "two")]

    def test_only_one_of_two_opposite_merges_happens(self):
        barrier = threading.Barrier(2)
        results = []
        delete = user_db.session.delete

        def slow_delete(obj):
            # widen the window between the checks and the delete
            threading.Event().wait(0.2)
            delete(obj)

        def merge(source_id, target_id):
            with self.app.app_context():
                barrier.wait()
                try:
                    merge_users(source_id, target_id, None, None)
                    results.append("merged")
                except Exception as exc:  # noqa: BLE001
                    results.append(type(exc).__name__)

        with patch.object(user_db.session, "delete", side_effect=slow_delete):
            threads = [
                threading.Thread(target=merge, args=self.ids),
                threading.Thread(target=merge, args=self.ids[::-1]),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(sorted(results), ["ValueError", "merged"])
        with self.app.app_context():
            remaining = [get_user_details(name) for name in ("one", "two")]
            self.assertEqual(sum(details is not None for details in remaining), 1)
