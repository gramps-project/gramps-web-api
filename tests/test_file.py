#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

"""Tests for file handling utilities."""

import os
from io import BytesIO

import pytest

from gramps_webapi.api.file import upload_file_local


@pytest.fixture
def base_dir(tmp_path):
    """Return a media base directory inside a temporary directory."""
    path = tmp_path / "media"
    path.mkdir()
    return path


def test_upload_file_local(base_dir):
    """A relative path is written inside the base directory."""
    upload_file_local(base_dir, "sub/dir/file.txt", BytesIO(b"content"))
    assert (base_dir / "sub" / "dir" / "file.txt").read_bytes() == b"content"


@pytest.mark.parametrize(
    "rel_path", ["../escaped.txt", "sub/../../escaped.txt", "/tmp/escaped.txt"]
)
def test_upload_file_local_outside_base_dir(base_dir, rel_path):
    """Paths escaping the base directory are rejected without writing."""
    with pytest.raises(ValueError):
        upload_file_local(base_dir, rel_path, BytesIO(b"pwned"))
    assert not (base_dir.parent / "escaped.txt").exists()
    assert not os.path.exists("/tmp/escaped.txt")
