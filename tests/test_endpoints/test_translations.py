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
        for translation in result.json:
            validate(
                instance=translation,
                schema=API_SCHEMA["definitions"]["Translation"],
                resolver=resolver,
            )


class TestTranslationsISOCode(unittest.TestCase):
    """Test cases for the /api/translations/{isocode} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_translations_isocode_endpoint_422(self):
        """Test response for an invalid parm."""
        # check 422 returned if missing parm
        result = self.client.get("/api/translations/fr")
        self.assertEqual(result.status_code, 422)
        # check 422 returned for bad parm
        result = self.client.get("/api/translations/fr?junk_parm=1")
        self.assertEqual(result.status_code, 422)

    def test_translations_isocode_endpoint_404(self):
        """Test response for a unsupported iso code."""
        # check 404 returned for non-existent place
        result = self.client.get('/api/translations/fake?strings=["Birth"]')
        self.assertEqual(result.status_code, 404)

    def test_translations_isocode_endpoint_400(self):
        """Test response for improperly formatted strings argument."""
        # check 404 returned for non-existent place
        result = self.client.get("/api/translations/fake?strings=[Birth]")
        self.assertEqual(result.status_code, 400)

    def test_translations_isocode_endpoint(self):
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

    def test_translations_isocode_endpoint_separator(self):
        """Test expected response using - or _ separator in iso language code."""
        result = self.client.get('/api/translations/zh-TW?strings=["Marriage"]')
        self.assertEqual(result.json[0], {"original": "Marriage", "translation": "婚姻"})
        result = self.client.get('/api/translations/zh_TW?strings=["Marriage"]')
        self.assertEqual(result.json[0], {"original": "Marriage", "translation": "婚姻"})
