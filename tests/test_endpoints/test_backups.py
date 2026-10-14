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

"""Tests for the /api/backups endpoints."""

import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState
from gramps.gen.utils.resourcepath import ResourcePath

from gramps_webapi.api.backup import _get_users, write_backup
from gramps_webapi.api.util import close_db, get_db_outside_request
from gramps_webapi.app import create_app
from gramps_webapi.auth import (
    add_user,
    delete_user,
    get_guid,
    get_tree_config,
    get_user_details,
    set_tree_config,
    user_db,
)
from gramps_webapi.auth.const import ROLE_ADMIN, ROLE_EDITOR, ROLE_OWNER
from gramps_webapi.const import (
    ENV_CONFIG_FILE,
    TEST_EMPTY_GRAMPS_AUTH_CONFIG,
    TREE_MULTI,
)

from gramps_webapi.util.task_state import (
    LOCK_BACKUP,
    LOCK_WRITE,
    acquire,
    mark_failed,
)

from . import BASE_URL, TEST_USERS
from .checks import check_success
from .util import fetch_header

BACKUPS_URL = BASE_URL + "/backups/"
RESTORE_URL = BASE_URL + "/backups/restore"
BACKUP_KEEP = 3
IMPORT_URL = BASE_URL + "/importers/gramps/file"

SMALL_TREE_PATH = os.path.join(
    ResourcePath().doc_dir, "example", "gramps", "data.gramps"
)
SMALL_TREE_PEOPLE = 60

MEMBER_NAMES = ["backup.json", "data.gramps", "tree.json", "users.json", "media.json"]


def _read_members(archive: bytes) -> dict[str, bytes]:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        return {
            member.name: tar.extractfile(member).read() for member in tar.getmembers()
        }


def _write_archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def _modify(archive: bytes, name: str, content: bytes, manifest=None) -> bytes:
    """Replace a member and update the manifest's checksums, like a crafted
    archive would."""
    members = _read_members(archive)
    members[name] = content
    manifest = manifest or json.loads(members["backup.json"])
    manifest["contents"] = [
        {
            "name": member_name,
            "size": len(member),
            "sha256": hashlib.sha256(member).hexdigest(),
        }
        for member_name, member in members.items()
        if member_name != "backup.json"
    ]
    members["backup.json"] = json.dumps(manifest).encode()
    return _write_archive(members)


class TestBackups(unittest.TestCase):
    """Test cases for creating and restoring backup archives."""

    @classmethod
    def setUpClass(cls):
        cls.name = "backups"
        cls.dbman = CLIDbManager(DbState())
        cls.dbpath, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        cls.backup_dir = tempfile.TemporaryDirectory()
        config = {
            "TREE": cls.name,
            "BACKUP_DIR": cls.backup_dir.name,
            "BACKUP_KEEP": BACKUP_KEEP,
        }
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EMPTY_GRAMPS_AUTH_CONFIG}):
            cls.test_app = create_app(config_from_env=False, config=config)
        cls.test_app.config["TESTING"] = True
        cls.client = cls.test_app.test_client()
        cls.tree = os.path.basename(cls.dbpath)
        with cls.test_app.app_context():
            user_db.create_all()
            for role in TEST_USERS:
                add_user(
                    name=TEST_USERS[role]["name"],
                    password=TEST_USERS[role]["password"],
                    role=role,
                )
            add_user(
                name="relative",
                password="xyz",
                fullname="A Relative",
                email="relative@example.com",
                role=ROLE_EDITOR,
            )
            set_tree_config(cls.tree, {"theme": "dark"})
        path = SMALL_TREE_PATH
        if not os.path.isfile(path):
            path += ".gz"
        with open(path, "rb") as f:
            small_tree = f.read()
        headers = fetch_header(cls.client, role=ROLE_OWNER)
        rv = cls.client.post(IMPORT_URL, data=io.BytesIO(small_tree), headers=headers)
        assert rv.status_code == 201
        cls.archive = cls._download(cls._create_backup()["id"])
        export_dir = cls.test_app.config["EXPORT_DIR"]
        os.makedirs(export_dir, exist_ok=True)
        cls.export_files = {
            name for name in os.listdir(export_dir) if name.endswith(".tar")
        }

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)
        cls.backup_dir.cleanup()

    @classmethod
    def _create_backup(cls) -> dict:
        headers = fetch_header(cls.client, role=ROLE_OWNER)
        rv = cls.client.post(BACKUPS_URL, headers=headers)
        assert rv.status_code == 201, rv.json
        return rv.json

    @classmethod
    def _download(cls, backup_id: str) -> bytes:
        headers = fetch_header(cls.client, role=ROLE_OWNER)
        rv = cls.client.get(BACKUPS_URL + backup_id, headers=headers)
        assert rv.status_code == 200
        data = rv.data
        rv.close()
        return data

    def _list(self) -> list[dict]:
        headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.get(BACKUPS_URL, headers=headers)
        self.assertEqual(rv.status_code, 200)
        return rv.json

    def _restore(self, archive: bytes, query: str = "", role=ROLE_OWNER):
        headers = fetch_header(self.client, role=role)
        return self.client.post(
            RESTORE_URL + query, data=io.BytesIO(archive), headers=headers
        )

    def test_backup_wrong_role(self):
        headers = fetch_header(self.client, role=ROLE_EDITOR)
        rv = self.client.post(BACKUPS_URL, headers=headers)
        self.assertEqual(rv.status_code, 403)
        rv = self.client.get(BACKUPS_URL, headers=headers)
        self.assertEqual(rv.status_code, 403)

    def test_archive_contents(self):
        members = _read_members(self.archive)
        self.assertEqual(list(members), MEMBER_NAMES)
        manifest = json.loads(members["backup.json"])
        self.assertEqual(manifest["format_version"], 1)
        self.assertEqual(manifest["tree"], {"id": self.tree, "name": self.name})
        self.assertEqual(manifest["backend"], "sqlite")
        self.assertEqual(manifest["object_counts"]["people"], SMALL_TREE_PEOPLE)
        self.assertFalse(manifest["protected"])
        for entry in manifest["contents"]:
            content = members[entry["name"]]
            self.assertEqual(entry["size"], len(content))
            self.assertEqual(entry["sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(
            json.loads(members["tree.json"]), {"config": {"theme": "dark"}}
        )
        users = {user["name"]: user for user in json.loads(members["users.json"])}
        self.assertEqual(
            users["relative"],
            {
                "name": "relative",
                "full_name": "A Relative",
                "email": "relative@example.com",
                "role": ROLE_EDITOR,
            },
        )
        media = json.loads(members["media.json"])
        self.assertEqual(len(media), manifest["media"]["count"])
        self.assertEqual(len(media), manifest["object_counts"]["media"])

    def test_metadata(self):
        headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.get(f"{BASE_URL}/metadata/", headers=headers)
        self.assertTrue(rv.json["server"]["backups"])
        self.assertEqual(rv.json["server"]["backup_keep"], BACKUP_KEEP)
        self.assertEqual(
            rv.json["server"]["rate_limit_backup"],
            [{"amount": 10, "window_seconds": 86400}],
        )

    def test_list(self):
        created = self._create_backup()
        (backup,) = [b for b in self._list() if b["id"] == created["id"]]
        self.assertEqual(backup, created)
        self.assertEqual(backup["manifest"]["tree"]["id"], self.tree)
        self.assertTrue(backup["restorable"])
        self.assertEqual(backup["size"], len(self._download(created["id"])))

    def test_not_restorable(self):
        """A backup this server can't restore is listed, but marked."""
        manifest = json.loads(_read_members(self.archive)["backup.json"])
        users = _read_members(self.archive)["users.json"]
        newer = _modify(
            self.archive,
            "users.json",
            users,
            {**manifest, "versions": {**manifest["versions"], "db_schema": 999}},
        )
        backup_id = "00000000-0000-4000-8000-000000000000"
        path = os.path.join(self.backup_dir.name, self.tree, f"{backup_id}.tar")
        with open(path, "wb") as f:
            f.write(newer)
        try:
            (backup,) = [b for b in self._list() if b["id"] == backup_id]
            self.assertFalse(backup["restorable"])
            headers = fetch_header(self.client, role=ROLE_OWNER)
            rv = self.client.post(
                f"{BACKUPS_URL}{backup_id}/restore?dry_run=true", headers=headers
            )
            self.assertEqual(rv.status_code, 422)
        finally:
            os.remove(path)

    def test_keep(self):
        """Creating a backup deletes the oldest ones beyond BACKUP_KEEP."""
        tree_dir = os.path.join(self.backup_dir.name, self.tree)
        for name in os.listdir(tree_dir):
            os.remove(os.path.join(tree_dir, name))
        # stored backups from earlier days, oldest first
        manifest = json.loads(_read_members(self.archive)["backup.json"])
        users = _read_members(self.archive)["users.json"]
        old_ids = []
        for day in range(1, BACKUP_KEEP + 1):
            backup_id = f"00000000-0000-4000-8000-00000000000{day}"
            archive = _modify(
                self.archive,
                "users.json",
                users,
                {**manifest, "created": f"2020-01-0{day}T00:00:00Z"},
            )
            with open(os.path.join(tree_dir, f"{backup_id}.tar"), "wb") as f:
                f.write(archive)
            old_ids.append(backup_id)
        new_id = self._create_backup()["id"]
        listed = [backup["id"] for backup in self._list()]
        self.assertEqual(listed, [new_id] + old_ids[:0:-1])

    def test_users_multi_tree(self):
        """In a multi-tree setup, site admins (users without a tree) are not
        part of a tree's backup."""
        with self.test_app.app_context():
            add_user(name="member_of_tree", password="x", role=1, tree=self.tree)
            try:
                with patch.dict(self.test_app.config, {"TREE": TREE_MULTI}):
                    names = {user["name"] for user in _get_users(self.tree)}
            finally:
                delete_user("member_of_tree")
        self.assertIn("member_of_tree", names)
        self.assertNotIn(TEST_USERS[ROLE_ADMIN]["name"], names)

    def test_download(self):
        backup_id = self._create_backup()["id"]
        headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.get(BACKUPS_URL + backup_id, headers=headers)
        self.assertEqual(rv.status_code, 200)
        self.assertRegex(
            rv.headers["Content-Disposition"],
            r"attachment; filename=gramps-web-backup-backups-\d{8}-\d{6}\.tar",
        )
        size = len(rv.data)
        rv.close()
        # downloads can be repeated and resumed
        rv = self.client.get(
            BACKUPS_URL + backup_id, headers={**headers, "Range": "bytes=10-"}
        )
        self.assertEqual(rv.status_code, 206)
        self.assertEqual(int(rv.headers["Content-Length"]), size - 10)
        rv.close()

    def test_delete(self):
        backup_id = self._create_backup()["id"]
        headers = fetch_header(self.client, role=ROLE_EDITOR)
        rv = self.client.delete(BACKUPS_URL + backup_id, headers=headers)
        self.assertEqual(rv.status_code, 403)
        headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.delete(BACKUPS_URL + backup_id, headers=headers)
        self.assertEqual(rv.status_code, 204)
        self.assertNotIn(backup_id, [backup["id"] for backup in self._list()])
        rv = self.client.delete(BACKUPS_URL + backup_id, headers=headers)
        self.assertEqual(rv.status_code, 404)

    def test_backup_of_other_tree(self):
        """Backups are only visible to the tree they were created for."""
        backup_id = self._create_backup()["id"]
        tree_dir = os.path.join(self.backup_dir.name, self.tree)
        other_dir = os.path.join(self.backup_dir.name, "other-tree")
        os.makedirs(other_dir, exist_ok=True)
        os.rename(
            os.path.join(tree_dir, f"{backup_id}.tar"),
            os.path.join(other_dir, f"{backup_id}.tar"),
        )
        self.assertNotIn(backup_id, [backup["id"] for backup in self._list()])
        headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.get(BACKUPS_URL + backup_id, headers=headers)
        self.assertEqual(rv.status_code, 404)

    def test_invalid_id(self):
        headers = fetch_header(self.client, role=ROLE_OWNER)
        for backup_id in ["notauuid", "..%2F..%2Fsecret"]:
            with self.subTest(backup_id=backup_id):
                rv = self.client.get(BACKUPS_URL + backup_id, headers=headers)
                self.assertEqual(rv.status_code, 404)

    def test_restore_stored(self):
        """A stored backup can be restored and is kept afterwards."""
        backup_id = self._create_backup()["id"]
        headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.post(
            f"{BACKUPS_URL}{backup_id}/restore?dry_run=true", headers=headers
        )
        self.assertEqual(rv.status_code, 200, rv.json)
        self.assertEqual(rv.json["data"]["unchanged"]["people"], SMALL_TREE_PEOPLE)
        self.assertIn(backup_id, [backup["id"] for backup in self._list()])
        # the restore's copy of the archive is removed
        self.assertEqual(self._export_files(), self.export_files)

    def _export_files(self) -> set[str]:
        export_dir = self.test_app.config["EXPORT_DIR"]
        return {name for name in os.listdir(export_dir) if name.endswith(".tar")}

    @contextmanager
    def _locked(self, lock_key: str) -> Iterator[str]:
        """Hold a lock on the tree as if another task were running."""
        holder = str(uuid.uuid4())
        with self.test_app.app_context():
            acquire(holder, "other_task", self.tree, None, lock_key)
        try:
            yield holder
        finally:
            with self.test_app.app_context():
                mark_failed(holder, "released by test")

    def test_restore_while_locked(self):
        """A restore is rejected while another task writes to the tree, and
        leaves no files behind."""
        backup_id = self._create_backup()["id"]
        headers = fetch_header(self.client, role=ROLE_OWNER)
        with self._locked(LOCK_WRITE) as holder:
            rv = self._restore(self.archive)
            self.assertEqual(rv.status_code, 409)
            self.assertEqual(rv.json["error"]["task"]["id"], holder)
            rv = self.client.post(f"{BACKUPS_URL}{backup_id}/restore", headers=headers)
            self.assertEqual(rv.status_code, 409)
            # dry runs don't write, so they aren't blocked
            rv = self._restore(self.archive, "?dry_run=true")
            self.assertEqual(rv.status_code, 200, rv.json)
        self.assertEqual(self._export_files(), self.export_files)
        self.assertIn(backup_id, [backup["id"] for backup in self._list()])

    def test_create_while_locked(self):
        """Backups of a tree are created one at a time, but not blocked by
        other tasks."""
        headers = fetch_header(self.client, role=ROLE_OWNER)
        with self._locked(LOCK_BACKUP):
            rv = self.client.post(BACKUPS_URL, headers=headers)
            self.assertEqual(rv.status_code, 409)
        with self._locked(LOCK_WRITE):
            rv = self.client.post(BACKUPS_URL, headers=headers)
            self.assertEqual(rv.status_code, 201, rv.json)

    def test_restore_wrong_role(self):
        rv = self._restore(self.archive, role=ROLE_EDITOR)
        self.assertEqual(rv.status_code, 403)

    def test_restore_nothing_selected(self):
        rv = self._restore(self.archive, "?data=false&tree_settings=false&users=false")
        self.assertEqual(rv.status_code, 422)

    def test_restore_invalid_archives(self):
        manifest = json.loads(_read_members(self.archive)["backup.json"])
        users = _read_members(self.archive)["users.json"]
        corrupted = _write_archive(
            {**_read_members(self.archive), "users.json": users + b" "}
        )
        cases = {
            "not a valid backup archive": b"not a backup archive",
            "users.json is truncated or corrupted": corrupted,
            "newer version of Gramps Web": _modify(
                self.archive, "users.json", users, {**manifest, "format_version": 2}
            ),
            "newer database schema": _modify(
                self.archive,
                "users.json",
                users,
                {**manifest, "versions": {**manifest["versions"], "db_schema": 999}},
            ),
            "Unexpected file in the archive: ../evil": _modify(
                self.archive, "../evil", b"x"
            ),
            "Invalid users.json": _modify(self.archive, "users.json", b'[{"name": 1}]'),
        }
        for message, archive in cases.items():
            with self.subTest(message=message):
                rv = self._restore(archive, "?dry_run=true")
                self.assertEqual(rv.status_code, 422)
                self.assertIn(message, rv.json["error"]["message"])

    def test_restore_dry_run_changes_nothing(self):
        with self.test_app.app_context():
            set_tree_config(self.tree, {"theme": "light"})
        try:
            rv = self._restore(self.archive, "?dry_run=true")
            self.assertEqual(rv.status_code, 200, rv.json)
            result = rv.json
            self.assertEqual(result["data"]["unchanged"]["people"], SMALL_TREE_PEOPLE)
            self.assertEqual(result["data"]["to_add"]["people"], 0)
            self.assertIsInstance(result["missing_media"], list)
            self.assertEqual(result["tree_settings"], {"changed": True})
            self.assertEqual(result["users"]["added"], [])
            self.assertIn("relative", result["users"]["skipped"])
            self.assertNotIn("index_tasks", result)
            with self.test_app.app_context():
                self.assertEqual(get_tree_config(self.tree), {"theme": "light"})
        finally:
            with self.test_app.app_context():
                set_tree_config(self.tree, {"theme": "dark"})

    def test_restore_data_post_processing_after_later_failure(self):
        """If a later part fails, the restored data still gets its usage and
        search index update."""
        with (
            patch(
                "gramps_webapi.api.tasks.restore_tree_config",
                side_effect=RuntimeError("boom"),
            ),
            patch(
                "gramps_webapi.api.tasks.update_search_indices_after_import",
                return_value=[],
            ) as update_indices,
        ):
            rv = self._restore(self.archive, "?users=false")
        self.assertEqual(rv.status_code, 500)
        update_indices.assert_called_once()

    def test_restore_tree_settings_only(self):
        with self.test_app.app_context():
            set_tree_config(self.tree, {"theme": "light"})
        rv = self._restore(self.archive, "?data=false&users=false")
        self.assertEqual(rv.status_code, 200, rv.json)
        self.assertNotIn("data", rv.json)
        self.assertNotIn("users", rv.json)
        self.assertEqual(rv.json["tree_settings"], {"changed": True})
        with self.test_app.app_context():
            self.assertEqual(get_tree_config(self.tree), {"theme": "dark"})

    def test_restore_users(self):
        with self.test_app.app_context():
            delete_user("relative")
        rv = self._restore(self.archive, "?data=false&tree_settings=false")
        self.assertEqual(rv.status_code, 200, rv.json)
        self.assertEqual(rv.json["users"]["added"], ["relative"])
        self.assertIn("owner", rv.json["users"]["skipped"])
        with self.test_app.app_context():
            details = get_user_details("relative")
        self.assertEqual(details["full_name"], "A Relative")
        self.assertEqual(details["email"], "relative@example.com")
        self.assertEqual(details["role"], ROLE_EDITOR)
        self.assertEqual(details["tree"], self.tree)

    def test_restore_users_caps_role(self):
        users = [{"name": "intruder", "full_name": None, "email": None, "role": 5}]
        archive = _modify(self.archive, "users.json", json.dumps(users).encode())
        rv = self._restore(archive, "?data=false&tree_settings=false")
        self.assertEqual(rv.status_code, 200, rv.json)
        self.assertEqual(rv.json["users"]["added"], ["intruder"])
        with self.test_app.app_context():
            details = get_user_details("intruder")
            delete_user("intruder")
        self.assertEqual(details["role"], ROLE_OWNER)
        self.assertLess(details["role"], ROLE_ADMIN)

    def test_restore_data(self):
        headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.post(f"{BASE_URL}/objects/delete/", headers=headers)
        self.assertIn(rv.status_code, (200, 202))
        self.assertEqual(len(check_success(self, f"{BASE_URL}/people/")), 0)
        rv = self._restore(self.archive, "?tree_settings=false&users=false")
        self.assertEqual(rv.status_code, 200, rv.json)
        self.assertEqual(rv.json["data"]["to_add"]["people"], SMALL_TREE_PEOPLE)
        self.assertIn("index_tasks", rv.json)
        self.assertEqual(
            len(check_success(self, f"{BASE_URL}/people/")), SMALL_TREE_PEOPLE
        )
        # the restored tree backs up to the same data
        members = _read_members(self._download(self._create_backup()["id"]))
        manifest = json.loads(members["backup.json"])
        original = json.loads(_read_members(self.archive)["backup.json"])
        self.assertEqual(manifest["object_counts"], original["object_counts"])


class TestBackupsNotConfigured(unittest.TestCase):
    """Without a backup directory, backups can't be stored."""

    @classmethod
    def setUpClass(cls):
        cls.name = "backups_not_configured"
        cls.dbman = CLIDbManager(DbState())
        dbpath, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        cls.tree = os.path.basename(dbpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EMPTY_GRAMPS_AUTH_CONFIG}):
            cls.test_app = create_app(config_from_env=False, config={"TREE": cls.name})
        cls.test_app.config["TESTING"] = True
        cls.client = cls.test_app.test_client()
        with cls.test_app.app_context():
            user_db.create_all()
            add_user(
                name=TEST_USERS[ROLE_OWNER]["name"],
                password=TEST_USERS[ROLE_OWNER]["password"],
                role=ROLE_OWNER,
            )

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_not_configured(self):
        headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.get(f"{BASE_URL}/metadata/", headers=headers)
        self.assertFalse(rv.json["server"]["backups"])
        rv = self.client.get(BACKUPS_URL, headers=headers)
        self.assertEqual(rv.status_code, 501)
        rv = self.client.post(BACKUPS_URL, headers=headers)
        self.assertEqual(rv.status_code, 501)

    def test_upload_restore(self):
        """Restoring an uploaded archive doesn't need a backup directory."""
        with self.test_app.app_context():
            user_id = get_guid(TEST_USERS[ROLE_OWNER]["name"])
            db_handle = get_db_outside_request(
                tree=self.tree, view_private=True, readonly=True, user_id=user_id
            )
            try:
                with tempfile.TemporaryDirectory() as directory:
                    path = os.path.join(directory, "backup.tar")
                    write_backup(
                        db_handle, tree=self.tree, tree_name=self.name, file_path=path
                    )
                    with open(path, "rb") as f:
                        archive = f.read()
            finally:
                close_db(db_handle)
        headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.post(
            RESTORE_URL + "?dry_run=true", data=io.BytesIO(archive), headers=headers
        )
        self.assertEqual(rv.status_code, 200, rv.json)
        self.assertEqual(rv.json["data"]["to_add"]["people"], 0)
