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

"""Tests for the OCR endpoint."""

import os
import shutil
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState
from PIL import Image, ImageDraw, ImageFont

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG

from . import BASE_URL

TEST_URL = BASE_URL + "/media/"


class TestOcr(unittest.TestCase):
    """Test text recognition (OCR)."""

    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API"
        cls.dbman = CLIDbManager(DbState())
        dirpath, _ = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        tree = os.path.basename(dirpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.media_base_dir = tempfile.mkdtemp()
        cls.app.config["MEDIA_BASE_DIR"] = cls.media_base_dir
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="user", password="123", role=ROLE_GUEST, tree=tree)
            add_user(name="owner", password="123", role=ROLE_OWNER, tree=tree)

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)
        shutil.rmtree(cls.media_base_dir)

    def test_get_ocr(self):
        """Test OCR."""
        # get token
        rv = self.client.post(
            "/api/token/", json={"username": "owner", "password": "123"}
        )
        access_token = rv.json["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # create image
        image = Image.new("RGB", (300, 100), "white")
        draw = ImageDraw.Draw(image)
        for font_name in ["Helvetica.ttf", "Arial.ttf", "DejaVuSans"]:
            try:
                font = ImageFont.truetype(font_name, 18)
                break
            except OSError:
                pass
        draw.text((10, 10), "OCR Demo", font=font, fill="black")

        # post image
        image_bytes_io = BytesIO()
        image.save(image_bytes_io, format="PNG")
        image_bytes = image_bytes_io.getvalue()
        rv = self.client.post(
            TEST_URL, headers=headers, data=image_bytes, content_type="image/jpeg"
        )
        assert rv.status_code == 201
        assert len(rv.json) == 1
        handle = rv.json[0]["handle"]

        # run OCR - not found
        rv = self.client.post(f"{TEST_URL}idontexist/ocr?lang=eng", headers=headers)
        assert rv.status_code == 404

        # run OCR - missing lang
        rv = self.client.post(f"{TEST_URL}idontexist/ocr", headers=headers)
        assert rv.status_code == 422

        # run OCR - string
        rv = self.client.post(f"{TEST_URL}{handle}/ocr?lang=eng", headers=headers)
        assert rv.status_code == 201
        data = rv.text
        assert "OCR Demo" in data

        # run OCR - data
        rv = self.client.post(
            f"{TEST_URL}{handle}/ocr?lang=eng&format=data", headers=headers
        )
        assert rv.status_code == 201
        data = rv.json
        assert "text" in data
        assert "OCR" in data["text"]

        # run OCR - boxes
        rv = self.client.post(
            f"{TEST_URL}{handle}/ocr?lang=eng&format=boxes", headers=headers
        )
        assert rv.status_code == 201
        data = rv.json
        assert "char" in data
        assert "O" in data["char"]
        assert "C" in data["char"]
        assert "R" in data["char"]

        # run OCR - hocr
        rv = self.client.post(
            f"{TEST_URL}{handle}/ocr?lang=eng&format=hocr", headers=headers
        )
        assert rv.status_code == 201
        assert "<?xml" in rv.text
