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
from unittest.mock import Mock, patch

from gramps.gen.lib import Media

from gramps_webapi.api.media import (
    ARCHIVE_GRACE_SECONDS,
    ARCHIVE_REUSE_MIN_REMAINING_SECONDS,
    MediaHandlerLocal,
    MediaHandlerS3,
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


def _media_db(*paths):
    """Return a mock database with media objects at the given paths."""
    media = []
    for i, path in enumerate(paths):
        obj = Media()
        obj.set_handle(str(i))
        obj.set_path(path)
        obj.set_checksum(str(i))
        media.append(obj)
    db = Mock()
    db.iter_media.side_effect = lambda: iter(media)
    db.get_number_of_media.return_value = len(media)
    return db


class TestMediaOutsideBaseDir(unittest.TestCase):
    """Media paths pointing outside the media folder are ignored."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.base_dir = root / "media"
        (self.base_dir / "sub").mkdir(parents=True)
        (self.base_dir / "sub" / "inside.jpg").write_bytes(b"inside")
        (self.base_dir / "..dots.jpg").write_bytes(b"dots")
        (self.base_dir / "alias.jpg").symlink_to(self.base_dir / "sub" / "inside.jpg")
        (self.base_dir / "loop").symlink_to(self.base_dir / "loop")
        (root / "link").symlink_to(self.base_dir)
        (root / "secret.txt").write_bytes(b"secret")
        self.db = _media_db(
            "sub/inside.jpg",
            str(self.base_dir / "sub" / "inside.jpg"),
            "../secret.txt",
            "sub/../../secret.txt",
            str(root / "secret.txt"),
            "alias.jpg",
            "loop",
            "a\0b",
            "..dots.jpg",
            # escapes the media folder by name, but not when resolved
            str(root / "link" / "sub" / "inside.jpg"),
        )
        self.names = ["sub/inside.jpg", "alias.jpg", "..dots.jpg"]
        self.handler = MediaHandlerLocal(str(self.base_dir))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_archive(self):
        zip_filename = Path(self.temp_dir.name, "archive.zip")
        self.handler.create_file_archive(self.db, zip_filename, include_private=True)
        with zipfile.ZipFile(zip_filename) as zip_file:
            assert zip_file.namelist() == self.names
            assert zip_file.read("alias.jpg") == b"inside"

    def test_media_size(self):
        # the symlink's target only counts once
        size = self.handler.get_media_size(db_handle=self.db)
        assert size == len(b"inside") + len(b"dots")

    def test_archive_s3(self):
        """Object storage archives contain no names that escape the archive."""
        handler = MediaHandlerS3("s3://bucket")
        file_handler = Mock()
        file_handler.get_file_object.side_effect = lambda: io.BytesIO(b"content")
        zip_filename = Path(self.temp_dir.name, "archive.zip")
        remote_keys = {"0", "2", "3", "5", "8"}
        with (
            patch.object(handler, "get_remote_keys", return_value=remote_keys),
            patch.object(handler, "get_file_handler", return_value=file_handler),
        ):
            handler.create_file_archive(self.db, zip_filename, include_private=True)
        with zipfile.ZipFile(zip_filename) as zip_file:
            assert zip_file.namelist() == self.names
