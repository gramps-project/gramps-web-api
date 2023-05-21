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

    def test_create_archive(self):
        """Create a media file archive."""
        headers = fetch_header(self.client, role=ROLE_EDITOR)
        rv = self.client.post(
            TEST_URL,
            headers=headers,
        )
        assert rv.status_code == 201
        assert "file_name" in rv.json
        assert "file_size" in rv.json
        assert "url" in rv.json
        rv = self.client.get(rv.json["url"], headers=headers)
        assert rv.status_code == 200
