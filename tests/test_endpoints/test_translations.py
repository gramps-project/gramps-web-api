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

from jsonschema import RefResolver, validate

from tests.test_endpoints import API_SCHEMA, get_test_client


class TestTranslations(unittest.TestCase):
    """Test cases for the /api/translations endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_translations_endpoint_schema(self):
        """Test all translations against the translation schema."""
        result = self.client.get("/api/translations/")
        # check some minimum number of expected translations found
        self.assertGreaterEqual(len(result.json), 39)
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Translations"],
            resolver=resolver,
        )


class TestTranslationsLanguage(unittest.TestCase):
    """Test cases for the /api/translations/{language} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_translations_language_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned if missing parm
        result = self.client.get("/api/translations/fr")
        self.assertEqual(result.status_code, 422)
        # check 422 returned for bad parm
        result = self.client.get("/api/translations/fr?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_translations_language_endpoint_404(self):
        """Test response for a unsupported language code."""
        # check 404 returned for non-existent place
        result = self.client.get('/api/translations/fake?strings=["Birth"]')
        self.assertEqual(result.status_code, 404)

    def test_translations_language_endpoint_400(self):
        """Test response for improperly formatted strings argument."""
        # check 404 returned for non-existent place
        result = self.client.get("/api/translations/fake?strings=[Birth]")
        self.assertEqual(result.status_code, 400)

    def test_translations_language_endpoint(self):
        """Test response for a translation."""
        # check a single expected translation was returned
        result = self.client.get('/api/translations/fr?strings=["Birth"]')
        self.assertEqual(len(result.json), 1)
        self.assertEqual(
            result.json[0], {"original": "Birth", "translation": "Naissance"}
        )
        # check multiple expected translations were returned
        result = self.client.get('/api/translations/fr?strings=["Birth", "Death"]')
        self.assertEqual(len(result.json), 2)
        self.assertEqual(
            result.json[0], {"original": "Birth", "translation": "Naissance"}
        )
        self.assertEqual(result.json[1], {"original": "Death", "translation": "Décès"})
