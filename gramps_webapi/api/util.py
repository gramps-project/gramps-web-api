#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Utility functions."""


from flask import current_app, g
from gramps.gen.utils.file import expand_media_path

from ..dbmanager import DbState


def get_dbstate() -> DbState:
    """Open the database and get the current state.

    Called before every request.
    """
    dbmgr = current_app.config["DB_MANAGER"]
    if "dbstate" not in g:
        g.dbstate = dbmgr.get_db()
    return g.dbstate


def get_media_base_dir():
    """Get the media base directory set in the database."""
    db = get_dbstate().db
    return expand_media_path(db.get_mediapath(), db)
