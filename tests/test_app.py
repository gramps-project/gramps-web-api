"""Tests for the `gramps_webapi.app` module."""

import unittest
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db.utils import make_database
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app


class TestDummy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API"
        cls.dbman = CLIDbManager(DbState())
        _, _name = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        with patch.dict("os.environ", {"TREE": cls.name}):
            app = create_app()
        app.config["TESTING"] = True
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def test_dummy_root(self):
        """Silly test just to get started."""
        rv = self.client.get("/")
        assert self.name.encode() in rv.data
