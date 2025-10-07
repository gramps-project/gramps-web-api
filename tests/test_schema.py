#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
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

"""Tests for the `gramps_webapi.api` module."""

import unittest
from importlib.resources import as_file, files

import yaml
from jsonschema import Draft4Validator


class TestSchema(unittest.TestCase):
    """Test cases to validate schema format."""

    def test_schema(self):
        """Check schema for validity."""
        # check it loads okay
        ref = files("gramps_webapi") / "data/apispec.yaml"
        with as_file(ref) as file_path:
            with open(file_path, encoding="utf-8") as file_handle:
                api_schema = yaml.safe_load(file_handle)
        # check structure
        Draft4Validator.check_schema(api_schema)
