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
import time
import unittest
import zipfile
from pathlib import Path

from gramps_webapi.api.media import ARCHIVE_GRACE_SECONDS
from gramps_webapi.auth.const import ROLE_EDITOR, ROLE_OWNER

from . import BASE_URL, get_test_client
from .util import fetch_header

TEST_URL = BASE_URL + "/media/archive/"


class TestMediaArchiv(unittest.TestCase):
    """Test cases for the /api/media/archive/ endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

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
        # still within the grace period, so not deleted yet
        self._create_archive(headers)
        assert path.exists()
        expired -= ARCHIVE_GRACE_SECONDS
        os.utime(path, (expired, expired))
        new = self._create_archive(headers)
        assert not path.exists()
        assert self._archive_path(new["file_name"]).exists()

    def test_archive_of_other_tree(self):
        """Archives can only be downloaded from the tree they were created for."""
        headers = fetch_header(self.client, role=ROLE_EDITOR)
        res = self._create_archive(headers)
        path = self._archive_path(res["file_name"])
        other_dir = path.parent.parent / "other-tree"
        other_dir.mkdir(exist_ok=True)
        path.rename(other_dir / path.name)
        rv = self.client.get(res["url"], headers=headers)
        assert rv.status_code == 404
