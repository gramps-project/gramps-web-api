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
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG
from sqlalchemy.exc import IntegrityError


class TestPerson(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API"
        cls.dbman = CLIDbManager(DbState())
        _, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        cls.config_file = tempfile.NamedTemporaryFile(delete=False)
        cls.user_db = tempfile.NamedTemporaryFile(delete=False)
        config = """TREE="Test Web API"
SECRET_KEY="C2eAhXGrXVe-iljXTjnp4paeRT-m68pq"
USER_DB_URI="sqlite:///{}"
""".format(
            cls.user_db.name
        )
        with open(cls.config_file.name, "w") as f:
            f.write(config)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: cls.config_file.name}):
            cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        cls.runner = CliRunner()

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)
        os.remove(cls.config_file.name)
        os.remove(cls.user_db.name)

    def test_add_delete_user(self):
        result = self.runner.invoke(
            cli, ["--config", self.config_file.name, "user", "add", "user", "123"]
        )
        assert result.exit_code == 0
        # try adding again
        result = self.runner.invoke(
            cli, ["--config", self.config_file.name, "user", "add", "user", "123"]
        )
        assert result.exception
        result = self.runner.invoke(
            cli, ["--config", self.config_file.name, "user", "delete", "user"]
        )
        assert result.exit_code == 0
        # try deleting again
        result = self.runner.invoke(
            cli, ["--config", self.config_file.name, "user", "delete", "user"]
        )
        assert result.exception
