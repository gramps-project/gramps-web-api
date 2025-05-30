#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
# Copyright (C) 2020      Christopher Horn
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

"""Unit test package for gramps_webapi."""

import gzip
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Optional

TEST_GRAMPSHOME = tempfile.mkdtemp()
os.environ["GRAMPSHOME"] = TEST_GRAMPSHOME
os.environ["GRAMPS_DATABASE_PATH"] = os.path.join(TEST_GRAMPSHOME, "gramps", "grampsdb")

from gramps.cli.clidbman import CLIDbManager
from gramps.cli.grampscli import CLIManager
from gramps.gen.config import get as getconfig
from gramps.gen.config import set as setconfig
from gramps.gen.const import USER_DIRLIST
from gramps.gen.db.base import DbReadBase
from gramps.gen.db.utils import import_as_dict, make_database
from gramps.gen.dbstate import DbState
from gramps.gen.user import User
from gramps.gen.utils.resourcepath import ResourcePath

from gramps_webapi.dbmanager import WebDbManager


class ExampleDbBase:
    """Gramps example database handler base class."""

    def __init__(self) -> None:
        """Initialize self."""
        for path in USER_DIRLIST:
            os.makedirs(path, exist_ok=True)
        _resources = ResourcePath()
        doc_dir = _resources.doc_dir
        os.environ["GRAMPS_RESOURCES"] = str(Path(_resources.data_dir).parent)
        self.path = os.path.join(doc_dir, "example", "gramps", "example.gramps")
        if os.path.isfile(self.path):
            self.is_zipped = False
        else:
            self.is_zipped = True
            self.tmp_gzdir = tempfile.mkdtemp()
            self.path_gz = os.path.join(
                doc_dir, "example", "gramps", "example.gramps.gz"
            )
            if not os.path.isfile(self.path_gz):
                raise ValueError(
                    "Neither example.gramps nor example.gramps.gz"
                    " found at {}".format(os.path.dirname(self.path_gz))
                )
            self.path = self._extract_to_tempfile()

    def _extract_to_tempfile(self) -> str:
        """Extract the example DB to a temp file and return the path."""
        with gzip.open(self.path_gz, "rb") as f_gzip:
            file_content = f_gzip.read()
            self.tmp_gzdir = tempfile.mkdtemp()
            path = os.path.join(self.tmp_gzdir, "example.gramps")
            with open(path, "wb") as f:
                f.write(file_content)
            return path


class ExampleDbInMemory(ExampleDbBase):
    """Gramps in-memory example database handler.

    Usage:
    ```
    exampledb = ExampleDbInMemory()
    db = exampledb.load()
    # ...
    exampledb.close()
    ```
    """

    def load(self) -> DbReadBase:
        """Return a DB instance with in-memory Gramps example DB."""
        return import_as_dict(self.path, User())

    def close(self) -> None:
        """Delete the temporary file if the DB has been extracted."""
        if self.is_zipped:
            shutil.rmtree(self.tmp_gzdir)


class ExampleDbSQLite(ExampleDbBase, WebDbManager):
    """Gramps SQLite example database handler.

    Instantiation should occur during test fixture setup, which should
    insure the temporary Gramps user directory structure was created.
    The database will be imported under there, and when testing is done
    the test fixture teardown is responsible for cleanup.
    """

    def __init__(self, name: Optional[str] = None) -> None:
        """Prepare and import the example DB."""
        ExampleDbBase.__init__(self)
        self.db_path = os.path.join(os.environ["GRAMPSHOME"], "gramps", "grampsdb")
        os.makedirs(self.db_path, exist_ok=True)
        setconfig("database.path", self.db_path)
        dbstate = DbState()
        dbman = CLIDbManager(dbstate)
        user = User()
        smgr = CLIManager(dbstate, True, user)
        smgr.do_reg_plugins(dbstate, uistate=None)
        self.path, import_name = dbman.import_new_db(self.path, User())
        self.name = name or import_name
        if name != import_name:
            dbman.rename_database(os.path.join(self.path, "name.txt"), self.name)
        WebDbManager.__init__(self, self.name)


def tearDownModule():
    """Test module tear down."""
    if TEST_GRAMPSHOME and os.path.isdir(TEST_GRAMPSHOME):
        shutil.rmtree(TEST_GRAMPSHOME)
