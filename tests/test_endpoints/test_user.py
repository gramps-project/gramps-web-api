"""Tests for the `gramps_webapi.api.resources.user` module."""

import unittest
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db import DbTxn
from gramps.gen.dbstate import DbState
from gramps.gen.lib import Person, Surname
from tests.test_endpoints import get_test_client

from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG


class TestUser(unittest.TestCase):
    """Test cases for the /api/user endpoints."""

    def setUp(self):
        self.name = "Test Web API"
        self.dbman = CLIDbManager(DbState())
        _, _name = self.dbman.create_new_db_cli(self.name, dbid="sqlite")
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        sqlauth = self.app.config["AUTH_PROVIDER"]
        sqlauth.create_table()
        sqlauth.add_user(name="user", password="123")

    def tearDown(self):
        self.dbman.remove_database(self.name)

    def test_change_password_wrong_method(self):
        rv = self.client.get("/api/user/password/change")
        assert rv.status_code == 405

    def test_change_password_no_token(self):
        rv = self.client.post(
            "/api/user/password/change",
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 401

    def test_change_password_wrong_old_pw(self):
        rv = self.client.post(
            "/api/login/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]
        rv = self.client.post(
            "/api/user/password/change",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"old_password": "012", "new_password": "456"},
        )
        assert rv.status_code == 403

    def test_change_password(self):
        rv = self.client.post(
            "/api/login/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]
        rv = self.client.post(
            "/api/user/password/change",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 201
        rv = self.client.post(
            "/api/login/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 403
        rv = self.client.post(
            "/api/login/", json={"username": "user", "password": "456"}
        )
        assert rv.status_code == 200

    def test_change_password_twice(self):
        rv = self.client.post(
            "/api/login/", json={"username": "user", "password": "123"}
        )
        assert rv.status_code == 200
        token = rv.json["access_token"]
        rv = self.client.post(
            "/api/user/password/change",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 201
        rv = self.client.post(
            "/api/user/password/change",
            headers={"Authorization": "Bearer {}".format(token)},
            json={"old_password": "123", "new_password": "456"},
        )
        assert rv.status_code == 403
