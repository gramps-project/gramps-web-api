"""Tests for the `gramps_webapi.api` module."""

import pytest

from gramps_webapi.api import create_app


@pytest.fixture
def client():
    """Mock client."""
    app = create_app()
    app.config["TESTING"] = True

    with app.test_client() as client:
        yield client


def test_dummy_root(client):
    """Silly test just to get started."""
    rv = client.get("/")
    assert b"Hello Gramps" in rv.data


def test_dummy_endpoint(client):
    """Silly test just to get started."""
    rv = client.get("/api/dummy")
    assert rv.json == {"key": "value"}
