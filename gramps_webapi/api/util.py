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
    db = get_dbstate()
    return expand_media_path(db.get_mediapath(), db)
