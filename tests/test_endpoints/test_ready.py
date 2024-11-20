#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2024      David Straub
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

"""Tests for the /ready endpoint."""

import unittest

from . import get_test_client


class TestBookmarks(unittest.TestCase):
    """Test cases for the /api/ready endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_ready(self):
        """Test authorization required."""
        rv = self.client.get("/ready")
        assert rv.status_code == 200
        assert rv.json == {"status": "ready"}
