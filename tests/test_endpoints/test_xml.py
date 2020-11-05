"""Tests for the /api/xml endpoints using example_gramps."""

import unittest

from . import get_test_client


class TestXml(unittest.TestCase):
    """Test cases for the /api/xml endpoint for a Gramps XML export."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_xml_endpoint(self):
        """Test reponse for xml."""
        rv = self.client.get("/api/xml/")
        assert rv.mime == "application/xml"

    def test_xml_endpoint_compress(self):
        """Test reponse for xml with compress option."""
        rv = self.client.get("/api/xml/?compress=1")
        assert rv.mime == "application/gz"
