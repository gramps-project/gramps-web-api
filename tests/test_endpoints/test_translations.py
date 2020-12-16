#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
# Copyright (C) 2020      Christopher Horn
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Tests for the /api/translations endpoints using example_gramps."""

import unittest

from . import BASE_URL, get_test_client
from .checks import (
    check_conforms_to_schema,
    check_invalid_semantics,
    check_invalid_syntax,
    check_requires_token,
    check_resource_missing,
    check_success,
)

TEST_URL = BASE_URL + "/translations/"


class TestTranslations(unittest.TestCase):
    """Test cases for the /api/translations endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_translations_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_translations_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "?junk")

    def test_get_translations_conforms_to_schema(self):
        """Test conformity to schema."""
        check_conforms_to_schema(self, TEST_URL, "Translations")

    def test_get_translations_expected_result(self):
        """Test some minimum set of expected values returned."""
        rv = check_success(self, TEST_URL)
        self.assertIsInstance(rv, type({}))
        self.assertGreaterEqual(len(rv), 39)
        self.assertIn("ar", rv)
        self.assertIn("zh_TW", rv)


class TestTranslationsLanguage(unittest.TestCase):
    """Test cases for the /api/translations/{language} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_translations_language_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + 'fr?strings=["Birth"]')

    def test_get_translations_language_validate_syntax(self):
        """Test invalid syntax."""
        check_invalid_syntax(self, TEST_URL + "fr?strings=[Birth]")

    def test_get_translations_language_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "fr")
        check_invalid_semantics(self, TEST_URL + "fr?junk_parm=1")

    def test_get_translations_language_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + 'fake?strings=["Birth"]')

    def test_get_translations_language_expected_result_single_value(self):
        """Test response for single translation."""
        rv = check_success(self, TEST_URL + 'fr?strings=["Birth"]')
        self.assertEqual(len(rv), 1)
        self.assertEqual(rv[0], {"original": "Birth", "translation": "Naissance"})

    def test_get_translations_language_expected_result_multiple_values(self):
        """Test response for multiple translations."""
        rv = check_success(self, TEST_URL + 'fr?strings=["Birth", "Death"]')
        self.assertEqual(len(rv), 2)
        self.assertEqual(rv[0], {"original": "Birth", "translation": "Naissance"})
        self.assertEqual(rv[1], {"original": "Death", "translation": "Décès"})
