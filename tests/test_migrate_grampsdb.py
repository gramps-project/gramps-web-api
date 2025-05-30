# Gramps Web API - A RESTful API for the Gramps genealogy program

# Copyright (C) 2020-2025      David Straub

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


"""Test the command line interface."""

import os
import pickle
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db.dbconst import KEY_TO_NAME_MAP, PLACE_KEY
from gramps.gen.dbstate import DbState
from gramps.gen.lib import Place, PlaceName
from sqlalchemy.sql import text

from gramps_webapi.__main__ import cli
from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE
from gramps_webapi.dbmanager import WebDbManager
from gramps_webapi.undodb import DbUndoSQLWeb


class TestMigrateCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API CLI"
        cls.dbman = CLIDbManager(DbState())
        _, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        cls.config_file = tempfile.NamedTemporaryFile(delete=False)
        cls.user_db = tempfile.NamedTemporaryFile(delete=False)
        config = f"""TREE="Test Web API CLI"
SECRET_KEY="C2eAhXGrXVe-iljXTjnp4paeRT-m68pq"
USER_DB_URI="sqlite:///{cls.user_db.name}"
"""
        with open(cls.config_file.name, "w") as f:
            f.write(config)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: cls.config_file.name}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        cls.runner = CliRunner()
        cls.db_manager = WebDbManager(cls.name, create_if_missing=False)
        tree = cls.db_manager.dirname
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="admin", password="123", role=ROLE_OWNER, tree=tree)
        cls.database_path = f"{cls.db_manager.path}/sqlite.db"

    @classmethod
    def tearDownClass(cls):
        # cls.dbman.remove_database(cls.name)
        # os.remove(cls.config_file.name)
        # os.remove(cls.user_db.name)
        pass

    def test_migrate_to_v21(self):
        db_handle = self.db_manager.get_db(readonly=False).db

        # manually add the old blob_data column and delete the new json_data column
        # to mimic version 20 schema
        with sqlite3.connect(self.database_path) as conn:
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE person ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE event ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE family ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE repository ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE media ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE place ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE source ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE note ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE citation ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE tag ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE person DROP COLUMN json_data")
            cursor.execute("ALTER TABLE event DROP COLUMN json_data")
            cursor.execute("ALTER TABLE family DROP COLUMN json_data")
            cursor.execute("ALTER TABLE repository DROP COLUMN json_data")
            cursor.execute("ALTER TABLE media DROP COLUMN json_data")
            cursor.execute("ALTER TABLE place DROP COLUMN json_data")
            cursor.execute("ALTER TABLE source DROP COLUMN json_data")
            cursor.execute("ALTER TABLE note DROP COLUMN json_data")
            cursor.execute("ALTER TABLE citation DROP COLUMN json_data")
            cursor.execute("ALTER TABLE tag DROP COLUMN json_data")
            cursor.execute("ALTER TABLE metadata DROP COLUMN json_data")
            conn.commit()

        # create a place
        handle = "123"
        place = Place()
        place.set_handle(handle)
        place.set_gramps_id("P0001")
        place.set_name(PlaceName(value="My Place"))
        place.set_alternative_names([PlaceName(value="Alternative Place")])
        place_raw = list(place.serialize())

        # commit to DB
        db_handle._txn_begin()
        db_handle.set_serializer("blob")
        db_handle._commit_raw(place_raw, PLACE_KEY)
        db_handle._txn_commit()
        db_handle._set_metadata("version", 20)
        assert db_handle.get_schema_version() == 20
        db_handle.set_serializer("json")

        # this gives an error because the column doesn't exist
        with pytest.raises(sqlite3.OperationalError):
            db_handle.get_place_from_handle(handle)

        # fetching a token works
        rv = self.client.post(
            "/api/token/", json={"username": "admin", "password": "123"}
        )
        token = rv.json["access_token"]

        # we can actually list the places correctly
        rv = self.client.get(
            "/api/places/", headers={"Authorization": f"Bearer {token}"}
        )

        # confirm we can read the schema info correctly
        rv = self.client.get(
            "/api/metadata/", headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 200
        assert rv.json["database"]["schema"] == "21.0.0"
        assert rv.json["database"]["actual_schema"] == 20

        # we can get (read-only) people just fine
        rv = self.client.get(
            "/api/people/", headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 200

        # trying to add a person will raise a 500 though
        person = {
            "primary_name": {
                "surname_list": [
                    {
                        "_class": "Surname",
                        "surname": "Doe",
                    }
                ],
                "first_name": "John",
            },
            "gender": 1,
        }

        rv = self.client.post(
            "/api/people/", json=person, headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 500

        # run the upgrade
        result = self.runner.invoke(
            cli,
            [
                "--config",
                self.config_file.name,
                "grampsdb",
                "migrate",
            ],
        )
        assert result.exit_code == 0

        # schema should be up to date now
        assert db_handle.get_schema_version() == 21

        # also here
        rv = self.client.get(
            "/api/metadata/", headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 200
        assert rv.json["database"]["schema"] == "21.0.0"
        assert rv.json["database"]["actual_schema"] == 21

        # can list places now
        rv = self.client.get(
            "/api/places/", headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 200
        assert rv.json[0]["name"]["value"] == "My Place"

        # can add person now
        rv = self.client.post(
            "/api/people/", json=person, headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 201


class TestMigrateAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API Migrate"
        cls.dbman = CLIDbManager(DbState())
        _, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        cls.config_file = tempfile.NamedTemporaryFile(delete=False)
        cls.user_db = tempfile.NamedTemporaryFile(delete=False)
        config = f"""TREE="Test Web API Migrate"
SECRET_KEY="C2eAhXGrXVe-iljXTjnp4paeRT-m68pq"
USER_DB_URI="sqlite:///{cls.user_db.name}"
"""
        with open(cls.config_file.name, "w") as f:
            f.write(config)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: cls.config_file.name}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        cls.db_manager = WebDbManager(cls.name, create_if_missing=False)
        tree = cls.db_manager.dirname
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="admin", password="123", role=ROLE_OWNER, tree=tree)
        cls.database_path = f"{cls.db_manager.path}/sqlite.db"

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)
        os.remove(cls.config_file.name)
        os.remove(cls.user_db.name)

    def test_migrate_from_v18(self):
        db_handle = self.db_manager.get_db(readonly=False).db

        # manually add the old blob_data column and delete the new json_data column
        # to mimic version 20 schema
        with sqlite3.connect(self.database_path) as conn:
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE person ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE event ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE family ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE repository ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE media ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE place ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE source ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE note ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE citation ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE tag ADD COLUMN blob_data BLOB")
            cursor.execute("ALTER TABLE person DROP COLUMN json_data")
            cursor.execute("ALTER TABLE event DROP COLUMN json_data")
            cursor.execute("ALTER TABLE family DROP COLUMN json_data")
            cursor.execute("ALTER TABLE repository DROP COLUMN json_data")
            cursor.execute("ALTER TABLE media DROP COLUMN json_data")
            cursor.execute("ALTER TABLE place DROP COLUMN json_data")
            cursor.execute("ALTER TABLE source DROP COLUMN json_data")
            cursor.execute("ALTER TABLE note DROP COLUMN json_data")
            cursor.execute("ALTER TABLE citation DROP COLUMN json_data")
            cursor.execute("ALTER TABLE tag DROP COLUMN json_data")
            cursor.execute("ALTER TABLE metadata DROP COLUMN json_data")
            conn.commit()

        # create a place
        handle = "123"
        place = Place()
        place.set_handle(handle)
        place.set_gramps_id("P0001")
        place.set_name(PlaceName(value="My Place"))
        place.set_alternative_names([PlaceName(value="Alternative Place")])
        place_raw = list(place.serialize())

        # commit to DB
        db_handle._txn_begin()
        db_handle.set_serializer("blob")
        db_handle._commit_raw(place_raw, PLACE_KEY)
        db_handle._txn_commit()
        db_handle._set_metadata("version", 20)
        assert db_handle.get_schema_version() == 20
        db_handle.set_serializer("json")

        undodb: DbUndoSQLWeb = db_handle.undodb
        with undodb.session_scope() as session:
            # delete the old_json and new_json columns of the changes table
            session.execute(text("ALTER TABLE changes DROP COLUMN old_json"))
            session.execute(text("ALTER TABLE changes DROP COLUMN new_json"))

        # fetching a token works
        rv = self.client.post(
            "/api/token/", json={"username": "admin", "password": "123"}
        )
        token = rv.json["access_token"]

        # we can actually list the places correctly
        rv = self.client.get(
            "/api/places/", headers={"Authorization": f"Bearer {token}"}
        )

        # confirm we can read the schema info correctly
        rv = self.client.get(
            "/api/metadata/", headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 200
        assert rv.json["database"]["schema"] == "21.0.0"
        assert rv.json["database"]["actual_schema"] == 20

        # we can get (read-only) people just fine
        rv = self.client.get(
            "/api/people/", headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 200

        # trying to add a person will raise a 500 though
        person = {
            "primary_name": {
                "surname_list": [
                    {
                        "_class": "Surname",
                        "surname": "Doe",
                    }
                ],
                "first_name": "John",
            },
            "gender": 1,
        }

        rv = self.client.post(
            "/api/people/", json=person, headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 500

        # run the upgrade
        rv = self.client.post(
            "/api/trees/-/migrate", headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 201

        # schema should be up to date now
        assert db_handle.get_schema_version() == 21

        # also here
        rv = self.client.get(
            "/api/metadata/", headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 200
        assert rv.json["database"]["schema"] == "21.0.0"
        assert rv.json["database"]["actual_schema"] == 21

        # can list places now
        rv = self.client.get(
            "/api/places/", headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 200
        assert rv.json[0]["name"]["value"] == "My Place"

        # can add person now
        rv = self.client.post(
            "/api/people/", json=person, headers={"Authorization": f"Bearer {token}"}
        )
        assert rv.status_code == 201
