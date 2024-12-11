#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2001-2006  Donald N. Allingham
# Copyright (C) 2009       Benny Malengier
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

"""Database loader utilitis derived from `grampscli`."""

from __future__ import annotations

import logging
import os
from uuid import uuid4

from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.const import PLUGINS_DIR, USER_PLUGINS
from gramps.gen.db.dbconst import DBBACKEND, DBLOCKFN, DBMODE_R, DBMODE_W
from gramps.gen.db.exceptions import DbUpgradeRequiredError
from gramps.gen.db.utils import make_database
from gramps.gen.dbstate import DbState
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.plug import BasePluginManager
from gramps.gen.recentfiles import recent_files
from gramps.gen.user import UserBase
from gramps.gen.utils.config import get_researcher
from gramps.gen.utils.configmanager import ConfigManager

from .undodb import DbUndoSQLWeb

_ = glocale.translation.gettext

LOG = logging.getLogger(__name__)


class DbLockedError(Exception):
    """Exception raised when a db is locked and write access is requested."""


def check_lock(dir_name: str, mode: str):
    """Raise if the mode is 'w' and the database is locked."""
    if mode == DBMODE_W and os.path.isfile(os.path.join(dir_name, DBLOCKFN)):
        raise DbLockedError(_("The database is locked."))


def get_title(filename: str) -> str:
    """Get the database title."""
    path = os.path.join(filename, "name.txt")
    try:
        with open(path, encoding="utf8") as ifile:
            title = ifile.readline().strip()
    except FileNotFoundError:
        title = filename
    return title


def get_postgres_credentials(directory, username, password):
    """Get the credentials for PostgreSQL."""
    config_file = os.path.join(directory, "settings.ini")
    config_mgr = ConfigManager(config_file)
    config_mgr.register("database.dbname", "")
    config_mgr.register("database.host", "")
    config_mgr.register("database.port", "")
    config_mgr.register("tree.uuid", "")

    if not os.path.exists(config_file):
        config_mgr.set("database.dbname", "gramps")
        config_mgr.set("database.host", config.get("database.host"))
        config_mgr.set("database.port", config.get("database.port"))
        config_mgr.set("tree.uuid", uuid4().hex)
        config_mgr.save()

    config_mgr.load()

    dbkwargs = {}
    for key in config_mgr.get_section_settings("database"):
        value = config_mgr.get("database." + key)
        if value:
            dbkwargs[key] = value
    if username:
        dbkwargs["user"] = username
    if password:
        dbkwargs["password"] = password

    return dbkwargs


class WebDbSessionManager:
    """Session manager derived from `CLIDbLoader` and `CLIManager`."""

    def __init__(self, dbstate: DbState, user: UserBase, user_id: str | None):
        """Initialize self."""
        self.dbstate = dbstate
        self._pmgr = BasePluginManager.get_instance()
        self.user = user
        self.user_id = user_id

    def read_file(
        self,
        filename,
        mode: str,
        username: str | None,
        password: str | None,
        force_schema_upgrade: bool = False,
    ):
        """Open a database from a file."""
        if (
            mode == DBMODE_W
            and os.path.exists(filename)
            and not os.access(filename, os.W_OK)
        ):
            mode = DBMODE_R
            LOG.warning(
                "%s. %s",
                _("Read only database"),
                _("You do not have write access " "to the selected file."),
            )

        dbid_path = os.path.join(filename, DBBACKEND)
        with open(dbid_path) as file_handle:
            dbid = file_handle.read().strip()

        db = make_database(dbid)

        def create_undo_manager():
            if dbid == "sqlite":
                dburl = f"sqlite:///{db.undolog}"
            elif dbid in ["postgresql", "sharedpostgresql"]:
                dbargs = get_postgres_credentials(filename, username, password)
                dburl = f"postgresql+psycopg2://{username}:{password}@{dbargs['host']}:{dbargs['port']}/{dbargs['dbname']}"
            if dbid == "sharedpostgresql":
                tree_id = db.dbapi.treeid
            else:
                tree_id = None
            return DbUndoSQLWeb(
                grampsdb=db, dburl=dburl, tree_id=tree_id, user_id=self.user_id
            )

        db._create_undo_manager = create_undo_manager

        self.dbstate.change_database(db)
        self.dbstate.db.disable_signals()

        # always use DMODE_R in load to avoid writing a lock file,
        # unless when upgrading the db
        mode_load = DBMODE_W if force_schema_upgrade else DBMODE_R
        self.dbstate.db.load(
            filename,
            callback=self.user.callback,
            mode=mode_load,
            username=username,
            password=password,
            force_schema_upgrade=force_schema_upgrade,
        )
        # set readonly correctly again
        self.dbstate.db.readonly = mode == DBMODE_R

        # but do check the necessity of schema upgrade!
        dbversion = self.dbstate.db.get_schema_version()
        if not self.dbstate.db.readonly and dbversion < self.dbstate.db.VERSION[0]:
            raise DbUpgradeRequiredError(dbversion, self.dbstate.db.VERSION[0])

    def open_activate(
        self,
        filename,
        mode,
        username=None,
        password=None,
        ignore_lock: bool = False,
    ):
        """Open and make a family tree active."""
        if not ignore_lock:
            check_lock(dir_name=filename, mode=mode)
        self.read_file(filename, mode, username, password)
        # Attempt to figure out the database title
        title = get_title(filename)
        self._post_load_newdb(filename, title)

    def _post_load_newdb(self, filename, title=None):
        """Called after load of a new database."""
        if not filename:
            return

        if filename[-1] == os.path.sep:
            filename = filename[:-1]
        name = os.path.basename(filename)
        self.dbstate.db.db_name = title
        if title:
            name = title

        # apply preferred researcher if loaded file has none
        res = self.dbstate.db.get_researcher()
        owner = get_researcher()
        # If the DB Owner Info is empty and
        # [default] Researcher is not empty and
        # database is empty, then copy default researcher to DB owner
        if res.is_empty() and not owner.is_empty() and self.dbstate.db.get_total() == 0:
            self.dbstate.db.set_researcher(owner)

        name_displayer.clear_custom_formats()
        name_displayer.set_name_format(self.dbstate.db.name_formats)
        fmt_default = config.get("preferences.name-format")
        name_displayer.set_default_format(fmt_default)

        self.dbstate.db.enable_signals()
        self.dbstate.signal_change()

        config.set("paths.recent-file", filename)

        recent_files(filename, name)

    def do_reg_plugins(self, dbstate, uistate, rescan=False):
        """Register the plugins at initialization time."""
        self._pmgr.reg_plugins(PLUGINS_DIR, dbstate, uistate, rescan=rescan)
        self._pmgr.reg_plugins(USER_PLUGINS, dbstate, uistate, load_on_reg=True)
        if rescan:  # supports updated plugin installs
            self._pmgr.reload_plugins()
