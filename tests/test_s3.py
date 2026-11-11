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
import tracemalloc
import unittest
import zipfile
from unittest.mock import Mock, patch

import boto3
import pytest
from moto import mock_aws

from gramps_webapi.api.media import MediaHandler
from gramps_webapi.api.s3 import get_object_keys_size
from .test_endpoints.test_media_archive import _media_db
from .test_endpoints.test_upload import get_image

BUCKET = "test-s3-bucket"
URL = f"s3://{BUCKET}"
URL_PREFIX = f"s3://{BUCKET}/mytree"


@pytest.fixture
def bucket():
    with mock_aws():
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


def _put(handler, checksum, content):
    client = boto3.client("s3", region_name="us-east-1")
    key = f"{handler.prefix}/{checksum}" if handler.prefix else checksum
    client.put_object(Bucket=BUCKET, Key=key, Body=content)


@pytest.mark.parametrize("url", [URL, URL_PREFIX])
def test_archive(bucket, tmp_path, url):
    """Files are archived under their media paths, each name once."""
    handler = MediaHandler(url)
    # larger than a copy chunk, so the content is copied in several reads
    big = os.urandom(3 * 1024 * 1024 + 1)
    _put(handler, "0", big)
    _put(handler, "1", b"small")
    _put(handler, "2", b"duplicate")
    db = _media_db("dir/big.bin", "small.txt", "small.txt", "missing.txt")
    zip_filename = tmp_path / "archive.zip"
    handler.create_file_archive(db, zip_filename, include_private=True)
    with zipfile.ZipFile(zip_filename) as zip_file:
        assert zip_file.namelist() == ["dir/big.bin", "small.txt"]
        assert zip_file.read("dir/big.bin") == big
        assert zip_file.read("small.txt") == b"small"
        assert zip_file.testzip() is None


def test_archive_object_deleted_after_listing(bucket, tmp_path):
    """Objects deleted while the archive is created are skipped."""
    handler = MediaHandler(URL)
    _put(handler, "0", b"gone")
    _put(handler, "1", b"kept")
    db = _media_db("gone.txt", "kept.txt")
    remote_keys = handler.get_remote_keys()
    boto3.client("s3", region_name="us-east-1").delete_object(Bucket=BUCKET, Key="0")
    zip_filename = tmp_path / "archive.zip"
    with patch.object(handler, "get_remote_keys", return_value=remote_keys):
        handler.create_file_archive(db, zip_filename, include_private=True)
    with zipfile.ZipFile(zip_filename) as zip_file:
        assert zip_file.namelist() == ["kept.txt"]


def test_archive_zip64(bucket, tmp_path):
    """Files beyond the zip64 limit are archived.

    Unlike writestr, a streamed entry must know its size in advance to
    decide on zip64, or zipfile raises once the limit is passed.
    """
    handler = MediaHandler(URL)
    content = b"x" * 5000
    _put(handler, "0", content)
    db = _media_db("large.bin")
    zip_filename = tmp_path / "archive.zip"
    with patch("zipfile.ZIP64_LIMIT", 1000):
        handler.create_file_archive(db, zip_filename, include_private=True)
        with zipfile.ZipFile(zip_filename) as zip_file:
            assert zip_file.read("large.bin") == content


class _LazyBody:
    """A streaming body that produces its content only when read."""

    def __init__(self, size):
        self.remaining = size

    def read(self, amt=None):
        assert amt is not None, "the whole body must not be read at once"
        n = min(amt, self.remaining)
        self.remaining -= n
        return b"x" * n

    def close(self):
        pass


def test_archive_memory(tmp_path):
    """Memory use does not grow with the size of the archived file."""
    size = 64 * 1024 * 1024
    handler = MediaHandler(URL)
    client = Mock()
    client.get_object.side_effect = lambda **kwargs: {
        "ContentLength": size,
        "Body": _LazyBody(size),
    }
    db = _media_db("large.bin")
    zip_filename = tmp_path / "archive.zip"
    with (
        patch.object(handler, "get_remote_keys", return_value={"0"}),
        patch("gramps_webapi.api.s3.get_client", return_value=client),
    ):
        tracemalloc.start()
        try:
            handler.create_file_archive(db, zip_filename, include_private=True)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
    assert peak < size / 16
    with zipfile.ZipFile(zip_filename) as zip_file:
        assert zip_file.getinfo("large.bin").file_size == size
