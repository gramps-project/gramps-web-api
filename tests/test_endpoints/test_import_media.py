#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2023      David M. Straub
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

"""Tests for the /api/media/archive/upload/zip endpoint."""

import os
import shutil
import tempfile
import unittest
import zipfile
from typing import Dict
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EMPTY_GRAMPS_AUTH_CONFIG


def get_headers(client, user: str, password: str) -> Dict[str, str]:
    """Get the auth headers for a specific user."""
    rv = client.post("/api/token/", json={"username": user, "password": password})
    access_token = rv.json["access_token"]
    return {"Authorization": "Bearer {}".format(access_token)}


class TestImporterMedia(unittest.TestCase):
    """Test cases for the /api/archive/upload/zip endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.name = "empty-import-media"
        cls.tmp_dir = tempfile.mkdtemp()
        cls.db_dir = os.path.join(cls.tmp_dir, "db")
        os.mkdir(cls.db_dir)
        cls.export_dir = os.path.join(cls.tmp_dir, "export")
        os.mkdir(cls.export_dir)
        cls.media_dir = os.path.join(cls.tmp_dir, "media")
        os.mkdir(cls.media_dir)
        cls.dbman = CLIDbManager(DbState())
        cls.dbpath, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EMPTY_GRAMPS_AUTH_CONFIG}):
            cls.test_app = create_app(
                {
                    "EXPORT_DIR": cls.export_dir,
                    "MEDIA_BASE_DIR": cls.media_dir,
                    "TREE": cls.name,
                },
            )
        cls.test_app.config["TESTING"] = True
        cls.client = cls.test_app.test_client()
        cls.tree = os.path.basename(cls.dbpath)
        with cls.test_app.app_context():
            user_db.create_all()
            add_user(
                name="owner",
                password="owner",
                role=ROLE_OWNER,
            )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir)
        cls.dbman.remove_database(cls.name)

    def test_import_media(self):
        """Test that importers are loaded also for a fresh db."""
        headers = get_headers(self.client, "owner", "owner")
        files = ["f1.jpg", "f2.jpg", "f3.jpg", "f4.jpg"]
        # write 4 random files with 1 kB, 2 kB, 3 kB, 4 kB
        for i, filename in enumerate(files):
            path = os.path.join(self.tmp_dir, filename)
            with open(path, "wb") as f:
                f.write(os.urandom((i + 1) * 1000))
        # upload 3 files
        for i, filename in enumerate(["f1.jpg", "f2.jpg", "f3.jpg"]):
            path = os.path.join(self.tmp_dir, filename)
            with open(path, "rb") as f:
                rv = self.client.post(
                    "/api/media/",
                    data=f.read(),
                    headers=headers,
                    content_type="image/jpeg",
                )
                assert rv.status_code == 201
        rv = self.client.get("/api/media/", headers=headers)
        assert rv.status_code == 200
        media_objects = rv.json
        assert len(media_objects) == 3
        rv = self.client.get("/api/trees/-", headers=headers)
        assert rv.status_code == 200
        assert rv.json["usage_media"] == 1000 + 2000 + 3000
        # delete f1 & f2
        for obj in media_objects:
            if obj["gramps_id"] in ["O0000", "O0001"]:
                checksum = obj["checksum"]
                path = os.path.join(self.media_dir, f"{checksum}.jpg")
                os.remove(path)
        rv = self.client.get("/api/media/?filemissing=1", headers=headers)
        assert rv.status_code == 200
        assert len(rv.json) == 2

        # zip f2 & f3, upload
        zip_path = os.path.join(self.tmp_dir, "zip1.zip")
        with zipfile.ZipFile(zip_path, "w") as fzip:
            for filename in ["f2.jpg", "f3.jpg"]:
                path = os.path.join(self.tmp_dir, filename)
                fzip.write(path)
        with open(zip_path, "rb") as f:
            rv = self.client.post(
                "/api/media/archive/upload/zip", headers=headers, data=f.read()
            )
            assert rv.status_code == 201
        zip_files = [fn for fn in os.listdir(self.export_dir) if fn.endswith(".zip")]
        assert len(zip_files) == 0  # temporary file deleted
        assert rv.json["missing"] == 2
        assert rv.json["uploaded"] == 1
        assert rv.json["failures"] == 0
        rv = self.client.get("/api/media/?filemissing=1", headers=headers)
        assert rv.status_code == 200
        assert len(rv.json) == 1
        rv = self.client.get("/api/trees/-", headers=headers)
        assert rv.status_code == 200
        assert rv.json["usage_media"] == 2000 + 3000
