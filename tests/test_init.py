"""Unit test package for gramps_webapi."""

import unittest

from gramps.gen.db.base import DbReadBase

from . import ExampleDb


class TestExampleDb(unittest.TestCase):
    def test_example_db(self):
        db = ExampleDb()
        self.assertIsInstance(db.load(), DbReadBase)
        db.close()
