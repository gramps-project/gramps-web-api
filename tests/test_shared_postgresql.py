#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Tree isolation tests for the SharedPostgreSQL backend.

SharedPostgreSQL stores every tree in the same tables, discriminated by a
`treeid` column. Everything going through the Gramps DB API is scoped by the
addon itself; these tests target the places where Gramps Web API issues raw
SQL and has to add `treeid` scoping by hand (structured object queries,
`preload_event_backlinks`).

Two trees are created in one database. Both contain objects with the *same*
handles but different content, so any unscoped query or join shows up as
duplicated or foreign rows.

Skipped unless `GRAMPSWEB_TEST_POSTGRES_URL` is set, e.g.
`postgresql://gramps:gramps@localhost:5432/gramps` (the database must be
named `gramps`, and the user must be allowed to create tables in it).
`GRAMPSWEB_TEST_ADDONS_DIR` must point to a directory containing the
`SharedPostgreSQL` addon.
"""

import os
import shutil
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from flask import Flask
from flask.testing import FlaskClient
from gramps.gen.const import USER_DIRLIST, USER_PLUGINS
from gramps.gen.db import DbTxn
from gramps.gen.lib import (
    Event,
    EventRef,
    EventType,
    Note,
    Person,
    Place,
    PlaceName,
    Surname,
)

from gramps_webapi.api.resources.util import preload_event_backlinks
from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_ADMIN, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager

ENV_POSTGRES_URL = "GRAMPSWEB_TEST_POSTGRES_URL"
ENV_ADDONS_DIR = "GRAMPSWEB_TEST_ADDONS_DIR"
ADDON = "SharedPostgreSQL"

BASE_URL = "/api"
PEOPLE_QUERY_URL = BASE_URL + "/people/query/"
NOTES_QUERY_URL = BASE_URL + "/notes/query/"

# handles shared by both trees
SHARED_PERSON = "P0001"
SHARED_EVENT = "E0001"
SHARED_PLACE = "PL0001"
SHARED_NOTE = "N0001"
# handles only present in one tree
ONLY_A_PERSON = "PA001"
ONLY_B_PERSON = "PB001"

POSTGRES_URL = os.getenv(ENV_POSTGRES_URL)


def _install_addon() -> None:
    """Copy the SharedPostgreSQL addon into the test user plugin directory."""
    addons_dir = os.getenv(ENV_ADDONS_DIR)
    if not addons_dir or not os.path.isdir(os.path.join(addons_dir, ADDON)):
        # fail rather than skip: the Postgres URL says we should run
        raise RuntimeError(
            f"{ENV_POSTGRES_URL} is set but {ENV_ADDONS_DIR} does not point "
            f"to a directory containing the {ADDON} addon."
        )
    for path in USER_DIRLIST:
        os.makedirs(path, exist_ok=True)
    os.makedirs(os.environ["GRAMPS_DATABASE_PATH"], exist_ok=True)
    shutil.copytree(
        os.path.join(addons_dir, ADDON),
        os.path.join(USER_PLUGINS, ADDON),
        dirs_exist_ok=True,
    )


def _populate(dbmgr: WebDbManager, label: str, extra_person: str) -> None:
    """Add a person with a birth event, place and note, plus one extra person."""
    dbstate = dbmgr.get_db(readonly=False)
    db = dbstate.db
    try:
        with DbTxn("populate", db) as trans:
            place = Place()
            place.set_handle(SHARED_PLACE)
            place.set_gramps_id("PL0001")
            place.set_title(f"{label}ville")
            place.set_name(PlaceName(value=f"{label}ville"))
            db.add_place(place, trans)

            event = Event()
            event.set_handle(SHARED_EVENT)
            event.set_gramps_id("E0001")
            event.set_type(EventType.BIRTH)
            event.set_description(f"Birth of {label}")
            event.set_place_handle(SHARED_PLACE)
            db.add_event(event, trans)

            note = Note(f"Note of {label}")
            note.set_handle(SHARED_NOTE)
            note.set_gramps_id("N0001")
            db.add_note(note, trans)

            person = Person()
            person.set_handle(SHARED_PERSON)
            person.set_gramps_id("I0001")
            person.set_gender(Person.FEMALE)
            surname = Surname()
            surname.set_surname(label)
            person.primary_name.add_surname(surname)
            person.primary_name.set_first_name("Shared")
            event_ref = EventRef()
            event_ref.set_reference_handle(SHARED_EVENT)
            person.add_event_ref(event_ref)
            person.set_birth_ref(event_ref)
            person.add_note(SHARED_NOTE)
            db.add_person(person, trans)

            person = Person()
            person.set_handle(extra_person)
            person.set_gramps_id("I0002")
            person.set_gender(Person.MALE)
            surname = Surname()
            surname.set_surname(label)
            person.primary_name.add_surname(surname)
            person.primary_name.set_first_name("Only")
            db.add_person(person, trans)
    finally:
        db.close()


def _delete_tree_rows(dbmgr: WebDbManager) -> None:
    """Remove all rows of a tree from the shared database."""
    dbstate = dbmgr.get_db(readonly=False)
    db = dbstate.db
    try:
        dbapi = db.dbapi
        treeid = dbapi.treeid
        dbapi.execute(
            "SELECT table_name FROM information_schema.columns "
            "WHERE column_name = 'treeid' AND table_schema = current_schema()"
        )
        tables = [row[0] for row in dbapi.fetchall()]
        dbapi.begin()
        for table in tables:
            dbapi.execute(f"DELETE FROM {table} WHERE treeid = ?", [treeid])
        dbapi.commit()
    finally:
        db.close()


@unittest.skipUnless(POSTGRES_URL, f"{ENV_POSTGRES_URL} not set")
class TestSharedPostgreSQLIsolation(unittest.TestCase):
    """Two trees in one SharedPostgreSQL database must not see each other."""

    pg_user: str | None
    pg_password: str | None
    app: Flask
    client: FlaskClient
    dbmgr_a: WebDbManager
    dbmgr_b: WebDbManager
    tree_a: str
    tree_b: str

    @classmethod
    def setUpClass(cls):
        _install_addon()
        url = urlparse(POSTGRES_URL)
        cls.pg_user = url.username
        cls.pg_password = url.password
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(
                config={
                    "TESTING": True,
                    "RATELIMIT_ENABLED": False,
                    "NEW_DB_BACKEND": "sharedpostgresql",
                    "POSTGRES_HOST": url.hostname or "localhost",
                    "POSTGRES_PORT": str(url.port or 5432),
                    "POSTGRES_USER": cls.pg_user,
                    "POSTGRES_PASSWORD": cls.pg_password,
                    "MEDIA_PREFIX_TREE": True,
                },
                config_from_env=False,
            )
        cls.client = cls.app.test_client()

        # tree A is created directly, as `create_app` or the CLI would
        cls.dbmgr_a = WebDbManager(
            dirname=WebDbManager.make_dirname(),
            name="Tree A",
            username=cls.pg_user,
            password=cls.pg_password,
            create_backend="sharedpostgresql",
        )
        cls.tree_a = cls.dbmgr_a.dirname
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="admin", password="123", role=ROLE_ADMIN, tree=cls.tree_a)
            add_user(name="owner_a", password="123", role=ROLE_OWNER, tree=cls.tree_a)

        # tree B is created through the API, like a multi-tree admin would
        rv = cls.client.post(
            BASE_URL + "/trees/",
            json={"name": "Tree B"},
            headers=cls._header("admin"),
        )
        assert rv.status_code == 201, rv.json
        cls.tree_b = rv.json["id"]
        cls.dbmgr_b = cls._dbmgr(cls.tree_b)
        with cls.app.app_context():
            add_user(name="owner_b", password="123", role=ROLE_OWNER, tree=cls.tree_b)

        _populate(cls.dbmgr_a, "Alpha", ONLY_A_PERSON)
        _populate(cls.dbmgr_b, "Beta", ONLY_B_PERSON)

    @classmethod
    def tearDownClass(cls):
        for dbmgr in (cls.dbmgr_a, cls.dbmgr_b):
            _delete_tree_rows(dbmgr)

    @classmethod
    def _dbmgr(cls, tree: str) -> WebDbManager:
        return WebDbManager(
            dirname=tree,
            username=cls.pg_user,
            password=cls.pg_password,
            create_if_missing=False,
        )

    @classmethod
    def _header(cls, username: str) -> dict[str, str]:
        rv = cls.client.post(
            BASE_URL + "/token/", json={"username": username, "password": "123"}
        )
        assert rv.json is not None
        return {"Authorization": f"Bearer {rv.json['access_token']}"}

    def _query(self, username: str, url: str, body: dict, status: int = 200):
        rv = self.client.post(url, json=body, headers=self._header(username))
        self.assertEqual(rv.status_code, status, rv.json)
        return rv

    def test_backend_is_shared_postgresql(self):
        for dbmgr in (self.dbmgr_a, self.dbmgr_b):
            dbstate = dbmgr.get_db()
            try:
                self.assertEqual(type(dbstate.db).__name__, "SharedPostgreSQL")
            finally:
                dbstate.db.close()
        self.assertNotEqual(self.tree_a, self.tree_b)

    def test_people_endpoint(self):
        for username, label, extra in [
            ("owner_a", "Alpha", ONLY_A_PERSON),
            ("owner_b", "Beta", ONLY_B_PERSON),
        ]:
            with self.subTest(username=username):
                rv = self.client.get(
                    BASE_URL + "/people/", headers=self._header(username)
                )
                self.assertEqual(rv.status_code, 200)
                self.assertEqual(
                    {person["handle"] for person in rv.json},
                    {SHARED_PERSON, extra},
                )
                rv = self.client.get(
                    BASE_URL + f"/people/{SHARED_PERSON}",
                    headers=self._header(username),
                )
                self.assertEqual(rv.status_code, 200)
                surnames = rv.json["primary_name"]["surname_list"]
                self.assertEqual(surnames[0]["surname"], label)

    def test_query_select_and_count(self):
        for username, extra in [
            ("owner_a", ONLY_A_PERSON),
            ("owner_b", ONLY_B_PERSON),
        ]:
            with self.subTest(username=username):
                rv = self._query(
                    username,
                    PEOPLE_QUERY_URL,
                    {"select": ["handle", "surname"], "count": True},
                )
                self.assertEqual(
                    sorted(item["handle"] for item in rv.json["items"]),
                    sorted([SHARED_PERSON, extra]),
                )
                self.assertEqual(rv.headers["X-Total-Count"], "2")

    def test_query_where(self):
        rv = self._query(
            "owner_b",
            PEOPLE_QUERY_URL,
            {
                "select": ["handle"],
                "where": [{"column": "gender", "op": "eq", "value": Person.MALE}],
                "count": True,
            },
        )
        self.assertEqual(rv.json["items"], [{"handle": ONLY_B_PERSON}])
        self.assertEqual(rv.headers["X-Total-Count"], "1")

    def test_query_path_join(self):
        """A path column joins person -> event -> place; each hop must stay
        in the caller's tree, or the shared handles produce extra rows."""
        for username, label in [("owner_a", "Alpha"), ("owner_b", "Beta")]:
            rv = self._query(
                username,
                PEOPLE_QUERY_URL,
                {
                    "select": ["handle", "birth.place.title"],
                    "where": [{"column": "handle", "op": "eq", "value": SHARED_PERSON}],
                },
            )
            self.assertEqual(
                rv.json["items"],
                [{"handle": SHARED_PERSON, "birth.place.title": f"{label}ville"}],
            )

    # gramps-object-query-language orders NULL as the smallest value, but
    # emits no NULLS FIRST/LAST, so PostgreSQL sorts NULL first in `desc`.
    @unittest.expectedFailure
    def test_query_order_by_path(self):
        rv = self._query(
            "owner_b",
            PEOPLE_QUERY_URL,
            {
                "select": ["handle", "birth.place.title"],
                "order_by": [{"column": "birth.place.title", "direction": "desc"}],
            },
        )
        self.assertEqual(
            [item["birth.place.title"] for item in rv.json["items"]],
            ["Betaville", None],
        )

    def test_query_exists(self):
        rv = self._query(
            "owner_b",
            PEOPLE_QUERY_URL,
            {
                "select": ["handle"],
                "where": [{"exists": {"relationship": "notes"}}],
                "count": True,
            },
        )
        self.assertEqual(rv.json["items"], [{"handle": SHARED_PERSON}])
        self.assertEqual(rv.headers["X-Total-Count"], "1")

    def test_query_exists_backlinks(self):
        rv = self._query(
            "owner_b",
            NOTES_QUERY_URL,
            {
                "select": ["handle", "text"],
                "where": [
                    {
                        "exists": {
                            "relationship": "backlinks",
                            "where": [
                                {"column": "_class", "op": "eq", "value": "Person"}
                            ],
                        }
                    }
                ],
            },
        )
        self.assertEqual(len(rv.json["items"]), 1)
        self.assertEqual(rv.json["items"][0]["handle"], SHARED_NOTE)
        self.assertIn("Beta", str(rv.json["items"][0]["text"]))

    def test_query_keyset_pagination(self):
        body = {"select": ["handle"], "limit": 1}
        rv = self._query("owner_b", PEOPLE_QUERY_URL, body)
        first = rv.json["items"]
        self.assertIsNotNone(rv.json["next_after"])
        rv = self._query(
            "owner_b", PEOPLE_QUERY_URL, {**body, "after": rv.json["next_after"]}
        )
        second = rv.json["items"]
        self.assertIsNone(rv.json["next_after"])
        self.assertEqual(
            sorted(item["handle"] for item in first + second),
            sorted([SHARED_PERSON, ONLY_B_PERSON]),
        )

    def test_query_after_handle_from_other_tree(self):
        """A cursor naming a handle that only exists in another tree must
        not resolve."""
        self._query(
            "owner_b",
            PEOPLE_QUERY_URL,
            {"select": ["handle"], "after": ONLY_A_PERSON},
            status=422,
        )

    def test_preload_event_backlinks(self):
        for dbmgr in (self.dbmgr_a, self.dbmgr_b):
            dbstate = dbmgr.get_db()
            try:
                index = preload_event_backlinks(dbstate.db)
            finally:
                dbstate.db.close()
            self.assertEqual(index, {SHARED_EVENT: [("Person", SHARED_PERSON)]})
