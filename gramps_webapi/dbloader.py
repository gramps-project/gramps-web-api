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

import logging
import os

from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.const import PLUGINS_DIR, USER_PLUGINS
from gramps.gen.db.dbconst import DBBACKEND, DBLOCKFN, DBMODE_R, DBMODE_W
from gramps.gen.db.utils import make_database
from gramps.gen.dbstate import DbState
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.plug import BasePluginManager
from gramps.gen.recentfiles import recent_files
from gramps.gen.utils.config import get_researcher

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


class WebDbSessionManager:
    """Session manager derived from `CLIDbLoader` and `CLIManager`."""

    def __init__(self, dbstate: DbState, user):
        """Initialize self."""
        self.dbstate = dbstate
        self._pmgr = BasePluginManager.get_instance()
        self.user = user

    def read_file(self, filename, mode: str, username: str, password: str):
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

        self.dbstate.change_database(db)
        self.dbstate.db.disable_signals()

        # always use DMODE_R in load to avoid writing a lock file
        self.dbstate.db.load(
            filename,
            callback=None,
            mode=DBMODE_R,
            username=username,
            password=password,
        )
        # set readonly correctly again
        self.dbstate.db.readonly = mode == DBMODE_R

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
