#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2021      David Straub
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

"""Test consistent version numbers."""

import unittest

import yaml
from pkg_resources import resource_filename

from gramps_webapi import __version__


class TestVersion(unittest.TestCase):
    """Test the version specifiers are consistent."""

    def test_version(self):
        """Test version in setup and apispec are equal."""
        with open(
            resource_filename("gramps_webapi", "data/apispec.yaml")
        ) as file_handle:
            schema = yaml.safe_load(file_handle)
        self.assertEqual(__version__, schema["info"]["version"])
