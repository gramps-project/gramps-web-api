"""Tests for the `gramps_webapi.api` module."""

import unittest
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db import DbTxn
from gramps.gen.dbstate import DbState
from gramps.gen.lib import Person, Surname

from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG


def _add_person(gender, first_name, surname, trans, db):
    person = Person()
    person.gender = gender
    _name = person.primary_name
    _name.first_name = first_name
    surname1 = Surname()
    surname1.surname = surname
    _name.set_surname_list([surname1])
    person.gramps_id = "person001"
    db.add_person(person, trans)


class TestPerson(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API"
        cls.dbman = CLIDbManager(DbState())
        _, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        sqlauth = cls.app.config["AUTH_PROVIDER"]
        sqlauth.create_table()
        sqlauth.add_user(name="user", password="123")

    def setUp(self):
        dbstate = self.app.config["DB_MANAGER"].get_db(force_unlock=True)
        with DbTxn("Add test objects", dbstate.db) as trans:
            _add_person(Person.MALE, "John", "Allen", trans, dbstate.db)
        dbstate.db.close()

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_person_endpoint(self):
        rv = self.client.get("/api/people/")
        # no authorization header!
        assert rv.status_code == 401
        # fetch a token and try again
        rv = self.client.post("/api/login/", data={"username": "user", "password": 123})
        token = rv.json["access_token"]
        rv = self.client.get(
            "/api/people/",
            headers={"Authorization": "Bearer {}".format(token)},
        )
        assert rv.status_code == 200
        it = rv.json[0]
        rv = self.client.get("/api/people/" + it["handle"] + "?profile")
        # no authorization header!
        assert rv.status_code == 401
        # fetch a token and try again
        rv = self.client.post("/api/login/", data={"username": "user", "password": 123})
        token = rv.json["access_token"]
        rv = self.client.get(
            "/api/people/" + it["handle"] + "?profile",
            headers={"Authorization": "Bearer {}".format(token)},
        )
        assert rv.status_code == 200
        assert len(rv.json["handle"]) > 20
        assert isinstance(rv.json["change"], int)
        assert rv.json["gramps_id"] == "person001"
        assert rv.json["profile"]["name_given"] == "John"
        assert rv.json["profile"]["name_surname"] == "Allen"
        assert rv.json["gender"] == 1  # male
        assert rv.json["private"] == False
        assert rv.json["birth_ref_index"] == -1
        assert rv.json["death_ref_index"] == -1

    def test_token_endpoint(self):
        rv = self.client.post("/api/login/", data={})
        # no username or password provided
        assert rv.status_code == 401
        rv = self.client.post("/api/login/", data={"username": "user", "password": 234})
        # wrong pw
        assert rv.status_code == 403
        rv = self.client.post(
            "/api/login/", data={"username": "admin", "password": 123}
        )
        # wrong user
        assert rv.status_code == 403
        rv = self.client.post("/api/login/", data={"username": "user", "password": 123})
        assert rv.status_code == 200
        assert "refresh_token" in rv.json
        assert "access_token" in rv.json

    def test_refresh_token_endpoint(self):
        rv = self.client.post("/api/refresh/", data={})
        # no authorization header!
        assert rv.status_code == 401
        # fetch a token and try again
        rv = self.client.post("/api/login/", data={"username": "user", "password": 123})
        refresh_token = rv.json["refresh_token"]
        access_token = rv.json["access_token"]
        # incorrectly send access token instead of refresh token!
        rv = self.client.post(
            "/api/refresh/",
            headers={"Authorization": "Bearer {}".format(access_token)},
        )
        assert rv.status_code == 422
        rv = self.client.post(
            "/api/refresh/",
            headers={"Authorization": "Bearer {}".format(refresh_token)},
        )
        assert rv.status_code == 200
        assert "refresh_token" not in rv.json
        assert "access_token" in rv.json
        assert rv.json["access_token"] != 1
