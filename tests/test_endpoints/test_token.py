"""Tests for the `gramps_webapi.api` module."""

import unittest

from tests.test_endpoints import get_test_client


class TestToken(unittest.TestCase):
    """Test cases for the /api/login and /api/refresh endpoints."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_token_endpoint(self):
        """Test login endpoint."""
        result = self.client.post("/api/login/")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json, {"access_token": 1, "refresh_token": 1})

    def test_refresh_token_endpoint(self):
        """Test refresh endpoint."""
        result = self.client.post("/api/refresh/")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json, {"access_token": 1})
