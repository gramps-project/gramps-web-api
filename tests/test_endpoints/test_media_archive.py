#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2023      David Straub
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

"""Tests for the file and thumbnail endpoints using example_gramps."""

import io
import os
import tempfile
import time
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import Mock

from gramps.gen.lib import Media

from gramps_webapi.api.media import (
    ARCHIVE_GRACE_SECONDS,
    ARCHIVE_REUSE_MIN_REMAINING_SECONDS,
    get_archive_name,
)
from gramps_webapi.auth.const import ROLE_EDITOR, ROLE_GUEST, ROLE_OWNER

from . import BASE_URL, get_test_client
from .util import fetch_header

TEST_URL = BASE_URL + "/media/archive/"


class TestMediaArchiv(unittest.TestCase):
    """Test cases for the /api/media/archive/ endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()
        # archives are named after their contents and outlive the test run, so
        # a shared export dir would hold the archives of earlier runs' trees
        cls.export_dir = tempfile.TemporaryDirectory()
        cls.export_dir_orig = cls.client.application.config["EXPORT_DIR"]
        cls.client.application.config["EXPORT_DIR"] = cls.export_dir.name

    @classmethod
    def tearDownClass(cls):
        cls.client.application.config["EXPORT_DIR"] = cls.export_dir_orig
        cls.export_dir.cleanup()

    def _create_archive(self, headers):
        rv = self.client.post(TEST_URL, headers=headers)
        assert rv.status_code == 201
        return rv.json

    def _archive_path(self, file_name):
        export_dir = self.client.application.config["EXPORT_DIR"]
        (path,) = Path(export_dir, "media_archives").glob(f"*/{file_name}")
        return path

    def test_create_archive(self):
        """Create a media file archive."""
        headers = fetch_header(self.client, role=ROLE_EDITOR)
        res = self._create_archive(headers)
        assert "file_name" in res
        assert "file_size" in res
        assert "url" in res
        rv = self.client.get(res["url"], headers=headers)
        assert rv.status_code == 200
        assert rv.mimetype == "application/zip"
        assert rv.headers["Content-Disposition"].startswith("attachment;")
        assert int(rv.headers["Content-Length"]) == res["file_size"]
        assert zipfile.is_zipfile(io.BytesIO(rv.data))
        rv.close()
        # downloads can be repeated and resumed
        rv = self.client.get(res["url"], headers=headers)
        assert rv.status_code == 200
        rv.close()
        rv = self.client.get(res["url"], headers={**headers, "Range": "bytes=10-"})
        assert rv.status_code == 206
        assert int(rv.headers["Content-Length"]) == res["file_size"] - 10
        rv.close()

    def test_reuse(self):
        """Requesting an archive of unchanged media returns the existing one."""
        headers = fetch_header(self.client, role=ROLE_EDITOR)
        first = self._create_archive(headers)
        path = self._archive_path(first["file_name"])
        mtime = path.stat().st_mtime_ns
        second = self._create_archive(headers)
        assert second == first
        assert path.stat().st_mtime_ns == mtime

    def test_reuse_needs_remaining_validity(self):
        """An archive that expires soon is created anew instead of reused."""
        headers = fetch_header(self.client, role=ROLE_EDITOR)
        res = self._create_archive(headers)
        path = self._archive_path(res["file_name"])
        retention = self.client.application.config["EXPORT_RETENTION_SECONDS"]
        old = time.time() - retention + ARCHIVE_REUSE_MIN_REMAINING_SECONDS / 2
        os.utime(path, (old, old))
        assert self._create_archive(headers)["file_name"] == res["file_name"]
        assert path.stat().st_mtime > old + 1

    def test_private_and_public_archives(self):
        """Users who can't see private records never get the same archive."""
        private = self._create_archive(fetch_header(self.client, role=ROLE_EDITOR))
        public = self._create_archive(fetch_header(self.client, role=ROLE_GUEST))
        assert private["file_name"] != public["file_name"]

    def test_expired_archive(self):
        """Expired archives cannot be downloaded and are deleted by a later export."""
        headers = fetch_header(self.client, role=ROLE_EDITOR)
        res = self._create_archive(headers)
        path = self._archive_path(res["file_name"])
        retention = self.client.application.config["EXPORT_RETENTION_SECONDS"]
        expired = time.time() - retention - 1
        os.utime(path, (expired, expired))
        rv = self.client.get(res["url"], headers=headers)
        assert rv.status_code == 404
        # an expired archive is created anew
        assert self._create_archive(headers)["file_name"] == res["file_name"]
        rv = self.client.get(res["url"], headers=headers)
        assert rv.status_code == 200
        rv.close()
        # other archives are deleted after the grace period
        old = path.parent / f"{uuid.uuid4()}.zip"
        old.write_bytes(b"")
        expired -= ARCHIVE_GRACE_SECONDS
        os.utime(old, (expired, expired))
        os.utime(path, (expired, expired))
        self._create_archive(headers)
        assert not old.exists()
        assert path.exists()

    def test_archive_of_other_tree(self):
        """Archives can only be downloaded from the tree they were created for."""
        headers = fetch_header(self.client, role=ROLE_EDITOR)
        res = self._create_archive(headers)
        path = self._archive_path(res["file_name"])
        other_dir = path.parent.parent / "other-tree"
        other_dir.mkdir(exist_ok=True)
        moved = other_dir / path.name
        path.rename(moved)
        try:
            rv = self.client.get(res["url"], headers=headers)
            assert rv.status_code == 404
        finally:
            moved.unlink()


class TestArchiveName(unittest.TestCase):
    """Archives are named after the media they contain."""

    def _db(self, *media):
        db = Mock()
        db.iter_media.side_effect = lambda: iter(media)
        return db

    def _media(self, handle, checksum, private=False):
        media = Media()
        media.set_handle(handle)
        media.set_path(f"{handle}.jpg")
        media.set_checksum(checksum)
        media.set_privacy(private)
        return media

    def test_name(self):
        a = self._media("a", "1")
        b = self._media("b", "2")
        name = get_archive_name(self._db(a, b), include_private=True)
        # independent of the order
        assert get_archive_name(self._db(b, a), include_private=True) == name
        changed = self._media("b", "3")
        assert get_archive_name(self._db(a, changed), include_private=True) != name
        assert get_archive_name(self._db(a), include_private=True) != name

    def test_private(self):
        public = self._media("a", "1")
        private = self._media("b", "2", private=True)
        name = get_archive_name(self._db(public, private), include_private=False)
        # private media don't matter for a public archive
        assert get_archive_name(self._db(public), include_private=False) == name
        # private and public archives never share a name
        assert get_archive_name(self._db(public), include_private=True) != name
