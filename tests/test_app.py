"""Tests for the `gramps_webapi.api` module."""

import unittest

from gramps_webapi.api import create_app


class TestDummy(unittest.TestCase):
    def setUp(self):
        """Mock client."""
        app = create_app()
        app.config["TESTING"] = True
        self.client = app.test_client()

    def tearDown(self):
        pass

    def test_dummy_root(self):
        """Silly test just to get started."""
        rv = self.client.get("/")
        assert b"Hello Gramps" in rv.data

    def test_dummy_endpoint(self):
        """Silly test just to get started."""
        rv = self.client.get("/api/dummy")
        assert rv.json == {"key": "value"}
