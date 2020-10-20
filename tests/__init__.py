"""Unit test package for gramps_webapi."""

import gzip
import os
import shutil
import tempfile
import unittest
from typing import Optional

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.config import get as getconfig
from gramps.gen.config import set as setconfig
from gramps.gen.db.base import DbReadBase
from gramps.gen.db.utils import import_as_dict, make_database
from gramps.gen.dbstate import DbState
from gramps.gen.user import User
from gramps.gen.utils.resourcepath import ResourcePath
from gramps.plugins.importer.importxml import importData


class ExampleDbBase:
    """Gramps example database handler base class."""

    def __init__(self) -> None:
        """Initialize self."""
        _resources = ResourcePath()
        doc_dir = _resources.doc_dir
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
        self.tmp_dbdir = None
        self.old_path = None

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


class ExampleDbSQLite(ExampleDbBase):
    """Gramps SQLite example database handler.

    Usage:
    ```
    exampledb = ExampleDbSQLite()
    exampledb.write()
    # ...
    exampledb.delete()
    ```

    Between `write` and `delete`, the Gramps database path will be
    changed to a temporary directory. The tree will be named "example".
    """

    def write(self) -> None:
        """Write the example DB to a SQLite DB and change the DB path."""
        self.tmp_dbdir = tempfile.mkdtemp()
        self.old_path = getconfig("database.path")
        setconfig("database.path", self.tmp_dbdir)
        dbman = CLIDbManager(DbState())
        dbman.import_new_db(self.path, User())

    def delete(self) -> None:
        """Change the DB path back and delete the SQLite DB."""
        if self.tmp_dbdir:
            shutil.rmtree(self.tmp_dbdir)
        if self.old_path:
            setconfig("database.path", self.old_path)
