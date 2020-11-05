"""Tests for the /api/translations endpoints using example_gramps."""

import unittest

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_test_client


class TestTranslations(unittest.TestCase):
    """Test cases for the /api/translations endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_translations_endpoint_schema(self):
        """Test all translations against the translation schema."""
        rv = self.client.get("/api/translations/")
        # check some minimum number of expected translations found
        assert len(rv.json) >= 39
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for translation in rv.json:
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
        rv = self.client.get("/api/translations/fr")
        assert rv.status_code == 422
        # check 422 returned for bad parm
        rv = self.client.get("/api/translations/fr?junk_parm=1")
        assert rv.status_code == 422

    def test_translations_isocode_endpoint_404(self):
        """Test response for a unsupported iso code."""
        # check 404 returned for non-existent place
        rv = self.client.get('/api/translations/fake?strings=["Birth"]')
        assert rv.status_code == 404

    def test_translations_isocode_endpoint_400(self):
        """Test response for improperly formatted strings argument."""
        # check 404 returned for non-existent place
        rv = self.client.get("/api/translations/fake?strings=[Birth]")
        assert rv.status_code == 400

    def test_translations_isocode_endpoint(self):
        """Test response for a translation."""
        # check a single expected translation was returned
        rv = self.client.get('/api/translations/fr?strings=["Birth"]')
        assert len(rv.json) == 1
        assert rv.json[0] == {"original": "Birth", "translation": "Naissance"}
        # check multiple expected translations were returned
        rv = self.client.get('/api/translations/fr?strings=["Birth", "Death"]')
        assert len(rv.json) == 2
        assert rv.json[0] == {"original": "Birth", "translation": "Naissance"}
        assert rv.json[1] == {"original": "Death", "translation": "Décès"}

    def test_translations_isocode_endpoint_separator(self):
        """Test expected response using - or _ separator in iso language code."""
        rv = self.client.get('/api/translations/zh-TW?strings=["Marriage"]')
        assert rv.json[0] == {"original": "Marriage", "translation": "婚姻"}
        rv = self.client.get('/api/translations/zh_TW?strings=["Marriage"]')
        assert rv.json[0] == {"original": "Marriage", "translation": "婚姻"}
