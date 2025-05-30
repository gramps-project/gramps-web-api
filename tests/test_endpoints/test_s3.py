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

import unittest
from unittest.mock import patch

import boto3
import pytest
from moto import mock_s3

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EXAMPLE_GRAMPS_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager
from tests import ExampleDbSQLite

from .test_upload import get_headers, get_image


class TestS3(unittest.TestCase):
    """Test cases with S3 media handling."""

    @classmethod
    def setup_class(cls):
        """Test class setup."""
        test_db = ExampleDbSQLite(name="example_gramps")
        with patch.dict(
            "os.environ", {ENV_CONFIG_FILE: TEST_EXAMPLE_GRAMPS_AUTH_CONFIG}
        ):
            test_app = create_app(
                config={
                    "TESTING": True,
                    "RATELIMIT_ENABLED": False,
                    "MEDIA_BASE_DIR": "s3://test-bucket",
                },
                config_from_env=False,
            )
        cls.client = test_app.test_client()
        with test_app.app_context():
            db_manager = WebDbManager(name=test_db.name, create_if_missing=False)
            tree = db_manager.dirname
            user_db.create_all()
            add_user(
                name="owner",
                password="owner",
                role=ROLE_OWNER,
                tree=tree,
            )

    @mock_s3
    def test_upload_new_media(self):
        """Add new media object."""
        boto3.resource("s3", region_name="us-east-1").create_bucket(
            Bucket="test-bucket"
        )
        img, checksum, size = get_image(0)
        headers = get_headers(self.client, "owner", "owner")
        rv = self.client.post(
            "/api/media/", data=img.read(), headers=headers, content_type="image/jpeg"
        )
        self.assertEqual(rv.status_code, 201)
        # check output
        out = rv.json
        self.assertEqual(len(out), 1)
        handle = out[0]["new"]["handle"]
        self.assertEqual(out[0]["old"], None)
        self.assertEqual(out[0]["type"], "add")
        # get the object
        rv = self.client.get(f"/api/media/{handle}", headers=headers)
        self.assertEqual(rv.status_code, 200)
        res = rv.json
        self.assertEqual(res["path"], f"{res['checksum']}.jpg")
        self.assertEqual(res["mime"], "image/jpeg")
        self.assertEqual(res["checksum"], checksum)
