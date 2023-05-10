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
from moto import mock_s3

from gramps_webapi.api.media import MediaHandler
from gramps_webapi.api.s3 import get_object_keys_size
from .test_endpoints.test_upload import get_image


BUCKET = "test-s3-bucket"
URL = f"s3://{BUCKET}"
URL_PREFIX = f"s3://{BUCKET}/mytree"


@pytest.fixture
def bucket():
    with mock_s3():
        res = boto3.resource("s3", region_name="us-east-1")
        res.create_bucket(Bucket=BUCKET)
        yield


def test_mediahandler(bucket):
    handler = MediaHandler(URL)
    assert handler.endpoint_url is None
    assert handler.bucket_name == BUCKET
    assert handler.get_remote_keys() == set()


def test_upload(bucket):
    handler = MediaHandler(URL)
    img, checksum, size = get_image(0)
    assert handler.get_remote_keys() == set()
    handler.upload_file(img, checksum, "image/jpeg")
    assert handler.get_remote_keys() == {checksum}
    img, checksum2, size = get_image(1)
    handler.upload_file(img, checksum2, "image/jpeg")
    assert handler.get_remote_keys() == {checksum, checksum2}


def test_upload_prefix(bucket):
    handler = MediaHandler(URL_PREFIX)
    img, checksum, size = get_image(0)
    assert handler.get_remote_keys() == set()
    handler.upload_file(img, checksum, "image/jpeg")
    assert handler.get_remote_keys() == {checksum}
    keys = list(
        get_object_keys_size(handler.bucket_name, "mytree", handler.endpoint_url).keys()
    )
    assert keys == [f"mytree/{checksum}"]
    img, checksum2, size = get_image(1)
    handler.upload_file(img, checksum2, "image/jpeg")
    assert handler.get_remote_keys() == {checksum, checksum2}
    keys = list(
        get_object_keys_size(handler.bucket_name, "mytree", handler.endpoint_url).keys()
    )
    assert sorted(keys) == sorted([f"mytree/{checksum}", f"mytree/{checksum2}"])
