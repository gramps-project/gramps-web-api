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

import os
import unittest
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

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

    @mock_aws
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

    @mock_aws
    def test_media_archive(self):
        """Media archives are served from object storage via redirect."""
        s3 = boto3.resource("s3", region_name="us-east-1")
        bucket = s3.create_bucket(Bucket="test-bucket")
        headers = get_headers(self.client, "owner", "owner")
        rv = self.client.post("/api/media/archive/", headers=headers)
        self.assertEqual(rv.status_code, 201)
        first_url = rv.json["url"]
        first_name = rv.json["file_name"]
        # the local copy is removed after the upload
        export_dir = self.client.application.config["EXPORT_DIR"]
        self.assertFalse(os.path.exists(os.path.join(export_dir, first_name)))
        rv = self.client.get(first_url, headers=headers)
        self.assertEqual(rv.status_code, 307)
        location = rv.headers["Location"]
        self.assertIn("media_archives/", location)
        self.assertIn(first_name, location)
        self.assertIn("response-content-disposition=attachment", location)
        # downloads can be repeated until the archive is replaced
        rv = self.client.get(first_url, headers=headers)
        self.assertEqual(rv.status_code, 307)
        # a new archive replaces the previous one
        rv = self.client.post("/api/media/archive/", headers=headers)
        self.assertEqual(rv.status_code, 201)
        second_name = rv.json["file_name"]
        keys = [obj.key for obj in bucket.objects.filter(Prefix="media_archives/")]
        self.assertEqual(len(keys), 1)
        self.assertTrue(keys[0].endswith(second_name))
        rv = self.client.get(first_url, headers=headers)
        self.assertEqual(rv.status_code, 404)
        rv = self.client.get(f"/api/media/archive/{second_name}", headers=headers)
        self.assertEqual(rv.status_code, 307)
