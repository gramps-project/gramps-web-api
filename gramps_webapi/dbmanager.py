"""Database manager class."""

import os

from gramps.cli.clidbman import CLIDbManager
from gramps.cli.grampscli import CLIManager
from gramps.cli.user import User
from gramps.gen.db.dbconst import DBLOCKFN
from gramps.gen.db.utils import get_dbid_from_path
from gramps.gen.dbstate import DbState


class WebDbManager:
    """Database manager class based on Gramps CLI."""

    ALLOWED_DB_BACKENDS = ["sqlite"]

    def __init__(self, name: str) -> None:
        """Initialize given a family tree name."""
        self.name = name
        self.path = self._get_path()
        self._check_backend()

    def _get_path(self) -> str:
        """Get the path of the family tree database."""
        dbstate = DbState()  # dbstate instance used only for this method
        dbman = CLIDbManager(dbstate)
        path = dbman.get_family_tree_path(self.name)
        if path is None:
            raise ValueError(
                "Database path for family tree '{}' not found".format(self.name)
            )
        return path

    def _check_backend(self) -> None:
        """Check that the backend is among the allowed backends."""
        backend = get_dbid_from_path(self.path)
        if backend not in self.ALLOWED_DB_BACKENDS:
            raise ValueError(
                "Database backend '{}' of tree '{}' not supported.".format(
                    backend, self.name
                )
            )

    def is_locked(self) -> bool:
        """Return a boolean whether the database is locked."""
        return os.path.isfile(os.path.join(self.path, DBLOCKFN))

    def break_lock(self) -> None:
        """Break the lock on a database."""
        if os.path.exists(os.path.join(self.path, DBLOCKFN)):
            os.unlink(os.path.join(self.path, DBLOCKFN))

    def get_db(self, force_unlock: bool = False) -> DbState:
        """Open the database and return a dbstate instance.

        If `force_unlock` is `True`, will break an existing lock (use with care!).
        """
        dbstate = DbState()
        user = User()
        smgr = CLIManager(dbstate, True, user)
        if force_unlock:
            self.break_lock()
        smgr.open_activate(self.path)
        return dbstate
