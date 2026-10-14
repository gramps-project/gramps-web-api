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

"""Tests that the media usage follows every change to the media objects.

The usage counts the files referred to by media objects, so it changes
whenever media objects are added, deleted or re-pointed - not only when a
file is uploaded. Without a task queue, run_task() executes the usage
recompute inline, so its result can be asserted on directly.
"""

import io
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EMPTY_GRAMPS_AUTH_CONFIG

from . import BASE_URL, TEST_USERS
from .test_upload import get_image
from .util import fetch_header

XML_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN"
"http://gramps-project.org/xml/1.7.1/grampsxml.dtd">
<database xmlns="http://gramps-project.org/xml/1.7.1/">
  <header><created date="2026-10-14" version="5.2.0"/></header>
"""


def _gramps_xml(media_paths: list[str]) -> bytes:
    """Return a Gramps XML file with one media object per path."""
    objects = "".join(
        f'<object handle="_usage{i}" change="0" id="O{i:04d}">'
        f'<file src="{path}" mime="image/png" description="{path}"/></object>'
        for i, path in enumerate(media_paths)
    )
    body = f"<objects>{objects}</objects>" if objects else ""
    return (XML_HEADER + body + "</database>\n").encode()


class TestMediaUsageSync(unittest.TestCase):
    """Check that paths changing media objects keep the media usage in sync."""

    @classmethod
    def setUpClass(cls):
        cls.name = "media_usage_sync"
        cls.dbman = CLIDbManager(DbState())
        cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        cls.media_base_dir = tempfile.mkdtemp()
        cls.backup_dir = tempfile.mkdtemp()
        config = {
            "TREE": cls.name,
            "MEDIA_BASE_DIR": cls.media_base_dir,
            "BACKUP_DIR": cls.backup_dir,
        }
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EMPTY_GRAMPS_AUTH_CONFIG}):
            cls.app = create_app(config_from_env=False, config=config)
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            for role in TEST_USERS:
                add_user(
                    name=TEST_USERS[role]["name"],
                    password=TEST_USERS[role]["password"],
                    role=role,
                )

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)
        shutil.rmtree(cls.media_base_dir)
        shutil.rmtree(cls.backup_dir)

    def setUp(self):
        self.headers = fetch_header(self.client, role=ROLE_OWNER)
        rv = self.client.post(f"{BASE_URL}/objects/delete/", headers=self.headers)
        self.assertIn(rv.status_code, (200, 202))
        self.assertEqual(self._usage(), 0)

    def _usage(self) -> int:
        rv = self.client.get(f"{BASE_URL}/trees/-", headers=self.headers)
        self.assertEqual(rv.status_code, 200)
        return rv.json["usage_media"]

    def _upload(self, color) -> tuple[list[dict], int]:
        """Upload a new media file, returning its transaction and size."""
        img, _, size = get_image(color)
        rv = self.client.post(
            f"{BASE_URL}/media/",
            data=img.read(),
            headers=self.headers,
            content_type="image/png",
        )
        self.assertEqual(rv.status_code, 201)
        return rv.json, size

    def _write_file(self, name: str, color) -> int:
        """Write a file to the media directory, returning its size."""
        img, _, size = get_image(color)
        with open(os.path.join(self.media_base_dir, name), "wb") as f:
            f.write(img.read())
        return size

    def test_import_counts_existing_files(self):
        """Imported media objects referring to files on disk count."""
        size = self._write_file("imported.png", 20)
        rv = self.client.post(
            f"{BASE_URL}/importers/gramps/file",
            data=io.BytesIO(_gramps_xml(["imported.png"])),
            headers=self.headers,
        )
        self.assertEqual(rv.status_code, 201)
        self.assertEqual(self._usage(), size)

    def test_restore_follows_backup_media(self):
        """Restoring adds and removes media objects, and their usage."""
        size = self._write_file("restored.png", 21)
        url = f"{BASE_URL}/importers/gramps/file/restore"
        rv = self.client.post(
            url, data=io.BytesIO(_gramps_xml(["restored.png"])), headers=self.headers
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(self._usage(), size)
        rv = self.client.post(
            url, data=io.BytesIO(_gramps_xml([])), headers=self.headers
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(self._usage(), 0)

    def test_restore_backup_archive(self):
        """Restoring a stored backup brings back its media usage."""
        trans, size = self._upload(22)
        rv = self.client.post(f"{BASE_URL}/backups/", headers=self.headers)
        self.assertEqual(rv.status_code, 201)
        backup_id = rv.json["id"]
        handle = trans[0]["handle"]
        rv = self.client.delete(f"{BASE_URL}/media/{handle}", headers=self.headers)
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(self._usage(), 0)
        rv = self.client.post(
            f"{BASE_URL}/backups/{backup_id}/restore"
            "?tree_settings=false&users=false",
            headers=self.headers,
        )
        self.assertEqual(rv.status_code, 200, rv.json)
        self.assertEqual(self._usage(), size)

    def test_undo_media_add(self):
        """Undoing the addition of a media object removes its usage."""
        trans, size = self._upload(23)
        self.assertEqual(self._usage(), size)
        rv = self.client.post(
            f"{BASE_URL}/transactions/?undo=1", json=trans, headers=self.headers
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(self._usage(), 0)

    def test_transaction_without_media_skips_recompute(self):
        """A transaction not touching media objects doesn't rescan the media."""
        from gramps_webapi.api.tasks import update_media_usage_task

        rv = self.client.post(
            f"{BASE_URL}/notes/",
            json={"_class": "Note", "text": {"_class": "StyledText", "string": "x"}},
            headers=self.headers,
        )
        self.assertEqual(rv.status_code, 201)
        with patch("gramps_webapi.api.tasks.run_task") as mock_run_task:
            rv = self.client.post(
                f"{BASE_URL}/transactions/?undo=1", json=rv.json, headers=self.headers
            )
        self.assertEqual(rv.status_code, 200)
        tasks = [call.args[0].name for call in mock_run_task.call_args_list]
        self.assertNotIn(update_media_usage_task.name, tasks)

    def test_merge_media(self):
        """Merging two media objects drops the usage of the merged-away file."""
        trans1, size1 = self._upload(24)
        trans2, size2 = self._upload(25)
        self.assertEqual(self._usage(), size1 + size2)
        phoenix, titanic = trans1[0]["handle"], trans2[0]["handle"]
        rv = self.client.post(
            f"{BASE_URL}/media/{phoenix}/merge/{titanic}", headers=self.headers
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(self._usage(), size1)

    def test_delete_all_objects(self):
        """Deleting all objects brings the media usage down to zero."""
        _, size = self._upload(26)
        self.assertEqual(self._usage(), size)
        rv = self.client.post(f"{BASE_URL}/objects/delete/", headers=self.headers)
        self.assertIn(rv.status_code, (200, 202))
        self.assertEqual(self._usage(), 0)
