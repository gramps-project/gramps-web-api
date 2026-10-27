#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026  Gramps Development Team
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

"""Tests for serving the frontend files from STATIC_PATH."""

import os
import tempfile
import unittest
import zlib
from unittest.mock import patch

from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG

# larger than COMPRESS_MIN_SIZE (500 bytes), so that it gets compressed
BUNDLE = "const answer = 42;\n" * 1000


class TestStaticFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.static_dir = tempfile.TemporaryDirectory()
        with open(os.path.join(cls.static_dir.name, "index.html"), "w") as f:
            f.write("<!doctype html><title>Gramps Web</title>")
        with open(os.path.join(cls.static_dir.name, "bundle.js"), "w") as f:
            f.write(BUNDLE)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(
                config={"TESTING": True, "STATIC_PATH": cls.static_dir.name},
                config_from_env=False,
            )
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.static_dir.cleanup()

    def test_compressed_file_not_modified(self):
        """A compressed frontend file answers its own ETag with 304."""
        headers = {"Accept-Encoding": "deflate"}
        rv = self.client.get("/bundle.js", headers=headers)
        assert rv.status_code == 200
        assert rv.headers["Content-Encoding"] == "deflate"
        assert zlib.decompress(rv.data).decode() == BUNDLE
        etag = rv.headers["ETag"]
        assert etag.endswith(':deflate"')
        rv = self.client.get("/bundle.js", headers={**headers, "If-None-Match": etag})
        assert rv.status_code == 304
        assert rv.data == b""
        rv = self.client.head("/bundle.js", headers={**headers, "If-None-Match": etag})
        assert rv.status_code == 304
        # a different ETag still gets the file
        rv = self.client.get(
            "/bundle.js", headers={**headers, "If-None-Match": '"other"'}
        )
        assert rv.status_code == 200
        assert zlib.decompress(rv.data).decode() == BUNDLE

    def test_uncompressed_file_not_modified(self):
        """Without compression, the ETag of the file itself gives 304."""
        headers = {"Accept-Encoding": "identity"}
        rv = self.client.get("/bundle.js", headers=headers)
        assert rv.status_code == 200
        assert "Content-Encoding" not in rv.headers
        etag = rv.headers["ETag"]
        rv = self.client.get("/bundle.js", headers={**headers, "If-None-Match": etag})
        assert rv.status_code == 304

    def test_index_html_not_stored(self):
        """index.html keeps Cache-Control: no-store."""
        rv = self.client.get("/", headers={"Accept-Encoding": "deflate"})
        assert rv.status_code == 200
        assert "no-store" in rv.headers["Cache-Control"]
