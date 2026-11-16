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

"""Tests for dry runs of database changes.

Run on SQLite, and on SharedPostgreSQL if `GRAMPSWEB_TEST_POSTGRES_URL` is set,
see `test_shared_postgresql.py`.
"""

import os
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

from flask import Flask
from gramps.gen.config import set as setconfig
from gramps.gen.db import DbTxn
from gramps.gen.lib import (
    Attribute,
    AttributeType,
    Event,
    EventRef,
    EventType,
    Family,
    Person,
    Surname,
)

from gramps_webapi.api.dry_run import dry_run
from gramps_webapi.api.resources.util import add_object, update_object
from gramps_webapi.api.util import close_db
from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager
from tests.test_shared_postgresql import (
    ENV_POSTGRES_URL,
    POSTGRES_URL,
    _delete_tree_rows,
    _install_addon,
)

FATHER = "DRYFATHER"
MOTHER = "DRYMOTHER"
OTHER = "DRYOTHER"
CUSTOM_EVENT_TYPE = "Dry run event type"
CUSTOM_ATTRIBUTE_TYPE = "Dry run attribute type"
NEW_FIRST_NAME = "Zyxwvutsrq"


def _person(handle: str, gramps_id: str, first_name: str, gender: int) -> Person:
    person = Person()
    person.set_handle(handle)
    person.set_gramps_id(gramps_id)
    person.set_gender(gender)
    surname = Surname()
    surname.set_surname("Dryrun")
    person.primary_name.add_surname(surname)
    person.primary_name.set_first_name(first_name)
    return person


class DryRunTestsBase:
    """Tests run for every backend; `app` and `dbmgr` are set up by the subclasses."""

    app: Flask
    dbmgr: WebDbManager

    @classmethod
    def _populate(cls):
        db = cls.dbmgr.get_db(readonly=False).db
        try:
            with DbTxn("populate", db) as trans:
                db.add_person(_person(FATHER, "I0001", "Father", Person.MALE), trans)
                db.add_person(_person(MOTHER, "I0002", "Mother", Person.FEMALE), trans)
                db.add_person(_person(OTHER, "I0003", "Other", Person.UNKNOWN), trans)
        finally:
            close_db(db)

    def _dry_run(self, apply):
        with self.app.app_context():
            return dry_run(self.dbmgr.dirname, "", apply)

    def _read(self, func):
        """Call `func` with a freshly opened read-only database."""
        db = self.dbmgr.get_db(readonly=True).db
        try:
            return func(db)
        finally:
            close_db(db)

    def _state(self):
        """Everything a dry run must leave unchanged."""

        def state(db):
            return {
                "father": db.get_raw_person_data(FATHER),
                "people": db.get_number_of_people(),
                "events": db.get_number_of_events(),
                "families": db.get_number_of_families(),
                "event_types": sorted(map(str, db.get_event_types())),
                "attribute_types": sorted(map(str, db.get_person_attribute_types())),
                "gender_stats": db.genderStats.name_stats(NEW_FIRST_NAME),
                "father_history": db.undodb.get_object_changes_state("Person", FATHER)[
                    1
                ],
            }

        return self._read(state)

    def test_returns_changes_with_side_effects(self):
        family = Family()
        family.set_handle("DRYFAMILY")
        family.set_father_handle(FATHER)
        family.set_mother_handle(MOTHER)

        result = self._dry_run(lambda db, trans: add_object(db, family, trans))

        changes = {(item["type"], item["_class"], item["handle"]) for item in result}
        self.assertEqual(
            changes,
            {
                ("add", "Family", "DRYFAMILY"),
                ("update", "Person", FATHER),
                ("update", "Person", MOTHER),
            },
        )
        father = next(item for item in result if item["handle"] == FATHER)
        self.assertEqual(father["old"]["family_list"], [])
        self.assertEqual(father["new"]["family_list"], ["DRYFAMILY"])

    def test_writes_nothing(self):
        before = self._state()

        def apply(db, trans):
            father = db.get_person_from_handle(FATHER)
            father.primary_name.set_first_name("Changed")
            event = Event()
            event.set_type(EventType((EventType.CUSTOM, CUSTOM_EVENT_TYPE)))
            add_object(db, event, trans)
            event_ref = EventRef()
            event_ref.set_reference_handle(event.handle)
            father.add_event_ref(event_ref)
            update_object(db, father, trans)
            person = _person("DRYNEW", "I0099", NEW_FIRST_NAME, Person.MALE)
            attribute = Attribute()
            attribute.set_type(
                AttributeType((AttributeType.CUSTOM, CUSTOM_ATTRIBUTE_TYPE))
            )
            attribute.set_value("value")
            person.add_attribute(attribute)
            add_object(db, person, trans)

        result = self._dry_run(apply)

        self.assertEqual(len(result), 3)
        self.assertEqual(self._state(), before)

    def test_error_propagates_and_writes_nothing(self):
        before = self._state()

        def apply(db, trans):
            father = db.get_person_from_handle(FATHER)
            father.primary_name.set_first_name("Changed")
            update_object(db, father, trans)
            raise ValueError("invalid change")

        with self.assertRaises(ValueError):
            self._dry_run(apply)
        self.assertEqual(self._state(), before)

    def test_real_write_afterwards(self):
        self._dry_run(lambda db, trans: db.remove_person(OTHER, trans))
        db = self.dbmgr.get_db(readonly=False).db
        try:
            with DbTxn("real change", db) as trans:
                other = db.get_person_from_handle(OTHER)
                other.primary_name.set_first_name("Really changed")
                db.commit_person(other, trans)
        finally:
            close_db(db)

        def first_name(db):
            return db.get_person_from_handle(OTHER).primary_name.get_first_name()

        self.assertEqual(self._read(first_name), "Really changed")


class TestDryRunSQLite(DryRunTestsBase, unittest.TestCase):
    """Dry runs on SQLite."""

    @classmethod
    def setUpClass(cls):
        db_path = os.environ["GRAMPS_DATABASE_PATH"]
        os.makedirs(db_path, exist_ok=True)
        setconfig("database.path", db_path)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(
                config={"TESTING": True, "RATELIMIT_ENABLED": False},
                config_from_env=False,
            )
        cls.dbmgr = WebDbManager(
            dirname=WebDbManager.make_dirname(), name="Dry run SQLite"
        )
        cls._populate()


@unittest.skipUnless(POSTGRES_URL, f"{ENV_POSTGRES_URL} not set")
class TestDryRunSharedPostgreSQL(DryRunTestsBase, unittest.TestCase):
    """Dry runs on SharedPostgreSQL."""

    @classmethod
    def setUpClass(cls):
        _install_addon()
        url = urlparse(POSTGRES_URL)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(
                config={
                    "TESTING": True,
                    "RATELIMIT_ENABLED": False,
                    "NEW_DB_BACKEND": "sharedpostgresql",
                    "POSTGRES_HOST": url.hostname or "localhost",
                    "POSTGRES_PORT": str(url.port or 5432),
                    "POSTGRES_USER": url.username,
                    "POSTGRES_PASSWORD": url.password,
                },
                config_from_env=False,
            )
        cls.dbmgr = WebDbManager(
            dirname=WebDbManager.make_dirname(),
            name="Dry run SharedPostgreSQL",
            username=url.username,
            password=url.password,
            create_backend="sharedpostgresql",
        )
        cls._populate()

    @classmethod
    def tearDownClass(cls):
        _delete_tree_rows(cls.dbmgr)
