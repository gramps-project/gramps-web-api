#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2000-2007  Donald N. Allingham
# Copyright (C) 2009       Brian G. Matherly
# Copyright (C) 2009       Gary Burton
# Copyright (C) 2020       David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Database manager class."""

import os
import uuid
from typing import Optional, Tuple

from gramps.cli.clidbman import NAME_FILE, CLIDbManager
from gramps.cli.user import User
from gramps.gen.config import config
from gramps.gen.db.dbconst import DBBACKEND, DBLOCKFN, DBMODE_R, DBMODE_W
from gramps.gen.db.utils import get_dbid_from_path, make_database
from gramps.gen.dbstate import DbState
from gramps.gen.user import UserBase

from .dbloader import WebDbSessionManager

# Module-level process-wide caches for tiny metadata files that are stable
# across requests.  Keyed by absolute directory path.
# Invalidated explicitly when the file is rewritten by this process.
_name_cache: dict[str, Optional[str]] = {}  # dirpath -> tree name
_backend_cache: dict[str, tuple[int, str]] = {}  # dirpath -> (mtime_ns, db backend id)


class WebDbManager:
    """Database manager class based on Gramps CLI."""

    ALLOWED_DB_BACKENDS = ["sqlite", "postgresql", "sharedpostgresql"]

    def __init__(
        self,
        name: Optional[str] = None,
        dirname: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        create_if_missing: bool = True,
        create_backend: str = "sqlite",
        ignore_lock: bool = False,
    ) -> None:
        """Initialize given a family tree name or subdirectory name (path)."""
        if dirname:
            self.dirname = dirname
            self._name_from_file = self._get_name(dirname=dirname)
            self.name = self._name_from_file or name or "unnamed tree"
        else:
            if name:
                self.name = name
                self._name_from_file = None  # name came from caller, not disk
                self.dirname = self._get_dirname(name=name)
            else:
                raise ValueError("One of (name, dirname) must be specified.")
        self.username = username
        self.password = password
        self.create_if_missing = create_if_missing
        self.create_backend = create_backend
        self.ignore_lock = ignore_lock
        self.path = self._get_path()
        self._check_backend()

    @property
    def dbdir(self) -> str:
        """Get the Gramps database directory's path."""
        return config.get("database.path")

    @staticmethod
    def make_dirname():
        """Make a new database directory name."""
        return str(uuid.uuid4())

    def _get_name(self, dirname: str) -> Optional[str]:
        """Get the database name, or None if not found/empty."""
        dirpath = os.path.join(self.dbdir, dirname)
        if dirpath in _name_cache:
            return _name_cache[dirpath]
        path_name = os.path.join(dirpath, NAME_FILE)
        if os.path.isfile(path_name):
            with open(path_name, "r", encoding="utf8") as name_file:
                name = name_file.readline().strip()
            if name:
                # Only cache non-empty names; missing/empty files are not
                # cached so a later write is picked up on the next call.
                _name_cache[dirpath] = name
                return name
        return None

    def _get_dirname(self, name: str) -> str:
        """Get the path of the family tree database."""
        dbstate = DbState()  # dbstate instance used only for this method
        dbman = CLIDbManager(dbstate)
        path = dbman.get_family_tree_path(name)
        if path is None:
            return self.make_dirname()
        return os.path.basename(path)

    def _get_path(self) -> str:
        """Get the path of the family tree database."""
        path = os.path.join(self.dbdir, self.dirname)
        if not os.path.isdir(path):
            if not self.create_if_missing:
                raise ValueError(
                    f"Database path '{self.dirname}'"
                    f"for family tree '{self.name}' not found"
                    f" in database directory {self.dbdir}"
                )
            self._create(path=path)
        return path

    def _create(self, path: str) -> None:
        """Create new database."""
        if self.create_backend not in self.ALLOWED_DB_BACKENDS:
            raise ValueError(
                f"Database backend '{self.create_backend}' not supported for new tree."
            )

        if not self.name:
            raise ValueError("Cannot create database if name not specified.")
        os.mkdir(path)

        # create name file
        path_name = os.path.join(path, NAME_FILE)
        with open(path_name, "w", encoding="utf8") as name_file:
            name_file.write(self.name)

        # create database
        make_database(self.create_backend)

        # create dbid file
        backend_path = os.path.join(path, DBBACKEND)
        with open(backend_path, "w", encoding="utf8") as backend_file:
            backend_file.write(self.create_backend)

        # cache the name written to disk so get_db() doesn't re-read name.txt
        self._name_from_file = self.name
        # populate module-level caches so subsequent requests skip disk reads
        _name_cache[path] = self.name
        try:
            backend_mtime = os.stat(backend_path).st_mtime_ns
        except OSError:
            backend_mtime = 0
        _backend_cache[path] = (backend_mtime, self.create_backend)

    def _check_backend(self) -> None:
        """Check that the backend is among the allowed backends."""
        dbbackend_path = os.path.join(self.path, DBBACKEND)
        try:
            current_mtime = os.stat(dbbackend_path).st_mtime_ns
        except OSError:
            current_mtime = 0
        cached = _backend_cache.get(self.path)
        if cached is not None and cached[0] == current_mtime:
            backend = cached[1]
        else:
            backend = get_dbid_from_path(self.path)
        if backend not in self.ALLOWED_DB_BACKENDS:
            raise ValueError(
                f"Database backend '{backend}' of tree '{self.name}' not supported."
            )
        _backend_cache[self.path] = (current_mtime, backend)
        self._dbid = backend

    def is_locked(self) -> bool:
        """Return a boolean whether the database is locked."""
        return os.path.isfile(os.path.join(self.path, DBLOCKFN))

    def break_lock(self) -> None:
        """Break the lock on a database."""
        if os.path.exists(os.path.join(self.path, DBLOCKFN)):
            os.unlink(os.path.join(self.path, DBLOCKFN))

    def get_db(
        self,
        user_id: str = "",
        readonly: bool = True,
        force_unlock: bool = False,
    ) -> DbState:
        """Open the database and return a dbstate instance.

        If `readonly` is `True` (default), write operations will fail (note,
        this is not enforced by Gramps but must be taken care of in Web
        API methods!).
        If `force_unlock` is `True`, will break an existing lock (use with care!).
        """
        dbstate = DbState()
        user = User()
        smgr = WebDbSessionManager(dbstate, user, user_id=user_id)
        smgr.do_reg_plugins(dbstate, uistate=None)
        if force_unlock:
            self.break_lock()
        mode = DBMODE_R if readonly else DBMODE_W
        smgr.open_activate(
            self.path,
            mode=mode,
            username=self.username,
            password=self.password,
            ignore_lock=self.ignore_lock,
            title=self._name_from_file or self.name,
            dbid=self._dbid,
        )
        return dbstate

    def rename_database(self, new_name: str) -> Tuple[str, str]:
        """Rename the database by writing the new value to the name.txt file.

        Returns old_name, new_name.
        """
        filepath = os.path.join(self.dbdir, self.dirname, NAME_FILE)
        with open(filepath, "r", encoding="utf8") as name_file:
            old_name = name_file.read().strip()
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Tree name must not be empty.")
        with open(filepath, "w", encoding="utf8") as name_file:
            name_file.write(new_name)
        self._name_from_file = new_name
        self.name = new_name
        # keep cache consistent so the next request doesn't re-read name.txt
        _name_cache[self.path] = new_name
        return old_name, new_name

    def upgrade_if_needed(
        self,
        user_id: Optional[str] = None,
        user: Optional[UserBase] = None,
    ):
        """Upgrade the Gramps database schema if needed."""
        dbstate = DbState()
        smgr = WebDbSessionManager(dbstate, user=user or User(), user_id=user_id)
        smgr.do_reg_plugins(dbstate, uistate=None)
        smgr.read_file(
            self.path,
            mode=DBMODE_W,
            username=self.username,
            password=self.password,
            force_schema_upgrade=True,
            dbid=self._dbid,
        )
