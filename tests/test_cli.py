#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Test the command line interface."""

import os
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.__main__ import cli
from gramps_webapi.app import create_app
from gramps_webapi.auth import get_user_details
from gramps_webapi.const import ENV_CONFIG_FILE
from gramps_webapi.dbmanager import WebDbManager


class TestCLI(unittest.TestCase):
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

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)
        os.remove(cls.config_file.name)
        os.remove(cls.user_db.name)

    def test_add_user_no_pw(self):
        result = self.runner.invoke(
            cli, ["--config", self.config_file.name, "user", "add", "userName0"]
        )
        assert result.exception

    def test_add_user_minimal(self):
        result = self.runner.invoke(
            cli,
            ["--config", self.config_file.name, "user", "add", "userName1", "pw1"],
        )
        assert result.exit_code == 0
        with self.app.app_context():
            details = get_user_details("userName1")
        assert details == {
            "name": "userName1",
            "role": 0,
            "email": None,
            "full_name": "",
            "tree": None,
        }
        assert details.get("fullname") is None

    def test_add_user_details(self):
        result = self.runner.invoke(
            cli,
            [
                "--config",
                self.config_file.name,
                "user",
                "add",
                "userName2",
                "pw2",
                "--fullname",
                "FullName2",
                "--email",
                "Email2",
                "--tree",
                "Tree2",
                "--role",
                "1",
            ],
        )
        assert result.exit_code == 0
        with self.app.app_context():
            details = get_user_details("userName2")
        assert details == {
            "name": "userName2",
            "full_name": "FullName2",
            "email": "Email2",
            "tree": "Tree2",
            "role": 1,
        }

    def test_add_delete_user(self):
        result = self.runner.invoke(
            cli, ["--config", self.config_file.name, "user", "add", "user", "123"]
        )
        assert result.exit_code == 0
        with self.app.app_context():
            assert get_user_details("user")
        # try adding again
        result = self.runner.invoke(
            cli, ["--config", self.config_file.name, "user", "add", "user", "123"]
        )
        assert result.exception
        result = self.runner.invoke(
            cli,
            ["--config", self.config_file.name, "user", "delete", "user"],
        )
        assert result.exit_code == 0
        with self.app.app_context():
            assert not get_user_details("user")
        # try deleting again
        result = self.runner.invoke(
            cli, ["--config", self.config_file.name, "user", "delete", "user"]
        )
        assert result.exception

    def test_search_reindex_incremental(self):
        tree = WebDbManager(name=self.name).dirname
        result = self.runner.invoke(
            cli,
            [
                "--config",
                self.config_file.name,
                "search",
                "--tree",
                tree,
                "index-incremental",
            ],
        )
        assert result.exit_code == 0

    def test_search_reindex_full(self):
        tree = WebDbManager(name=self.name).dirname
        result = self.runner.invoke(
            cli,
            [
                "--config",
                self.config_file.name,
                "search",
                "--tree",
                tree,
                "index-full",
            ],
        )
        assert result.exit_code == 0

    def test_search_reindex_incremental_notree(self):
        tree = WebDbManager(name=self.name).dirname
        result = self.runner.invoke(
            cli,
            [
                "--config",
                self.config_file.name,
                "search",
                "index-incremental",
            ],
        )
        assert result.exit_code == 0

    def test_search_reindex_full_notree(self):
        tree = WebDbManager(name=self.name).dirname
        result = self.runner.invoke(
            cli,
            [
                "--config",
                self.config_file.name,
                "search",
                "index-full",
            ],
        )
        assert result.exit_code == 0
