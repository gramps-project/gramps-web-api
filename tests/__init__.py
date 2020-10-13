"""Unit test package for gramps_webapi."""

import gzip
import os
import tempfile
import unittest

from gramps.gen.db.base import DbReadBase
from gramps.gen.db.utils import import_as_dict
from gramps.gen.user import User
from gramps.gen.utils.resourcepath import ResourcePath


class ExampleDb:
    """Gramps example database handler."""

    def __init__(self) -> None:
        """Initialize self."""
        _resources = ResourcePath()
        doc_dir = _resources.doc_dir
        self.path_gz = os.path.join(doc_dir, "example", "gramps", "example.gramps.gz")
        if not os.path.isfile(self.path_gz):
            raise ValueError("example.gramps not found at {}".format(self.path_gz))
        self.path = None

    def load(self) -> DbReadBase:
        """Extract the example DB to a temp file and return a DB instance."""
        with gzip.open(self.path_gz, "rb") as f_gzip:
            file_content = f_gzip.read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".gramps") as f:
                f.write(file_content)
                self.path = f.name
        return import_as_dict(self.path, User())

    def close(self) -> None:
        """Delete the temporary file."""
        if self.path is not None:
            os.remove(self.path)
