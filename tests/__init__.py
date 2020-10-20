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
        self.path = os.path.join(doc_dir, "example", "gramps", "example.gramps")
        if os.path.isfile(self.path):
            self.is_zipped = False
        else:
            self.is_zipped = True
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
            with tempfile.NamedTemporaryFile(delete=False, suffix=".gramps") as f:
                f.write(file_content)
                return f.name

    def load(self) -> DbReadBase:
        """Return a DB instance with the Gramps example DB."""
        return import_as_dict(self.path, User())

    def close(self) -> None:
        """Delete the temporary file if the DB has been extracted."""
        if self.is_zipped:
            os.remove(self.path)
