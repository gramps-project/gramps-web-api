"""Tests for the `gramps_webapi.api` module."""

import unittest

from jsonschema import validate

from . import get_test_client


class TestToken(unittest.TestCase):
    """Test cases for the /api/login and /api/refresh endpoints."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_token_endpoint(self):
        """Test login endpoint."""
        response_value = self.client.post("/api/login/", data={})
        assert response_value.status_code == 200
        assert response_value.json == {"access_token": 1, "refresh_token": 1}

    def test_refresh_token_endpoint(self):
        """Test refresh endpoint."""
        response_value = self.client.post("/api/refresh/")
        assert response_value.status_code == 200
        assert response_value.json == {"access_token": 1}
