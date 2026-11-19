"""Set up the dev container's family trees and users (multi-tree mode).

Creates two trees with fixed IDs:

- ``example``: the Gramps example tree, including its media files
- ``empty``: an empty tree

and one user per role for each tree (password = user name), plus a
tree-less admin. Uses the Gramps Python API only; never the ``gramps``
executable, which can fall back to opening the GUI.

Expects the dev container's environment (GRAMPSWEB_TREE="*",
GRAMPS_DATABASE_PATH, GRAMPSWEB_USER_DB_URI, GRAMPSWEB_MEDIA_BASE_DIR, ...).
"""

import os
import shutil

from gramps.gen.config import config

from gramps_webapi.api.resources.util import run_import
from gramps_webapi.app import create_app
from gramps_webapi.auth import User, add_user, user_db
from gramps_webapi.auth.const import (
    ROLE_ADMIN,
    ROLE_CONTRIBUTOR,
    ROLE_EDITOR,
    ROLE_MEMBER,
    ROLE_OWNER,
)
from gramps_webapi.dbmanager import WebDbManager

EXAMPLE_DIR = "/usr/local/share/doc/gramps/example/gramps"
EXAMPLE_FILE = os.path.join(EXAMPLE_DIR, "example.gramps")

TREES = {"example": "Example Tree", "empty": "Empty Tree"}

ROLES = {
    "owner": ROLE_OWNER,
    "editor": ROLE_EDITOR,
    "contributor": ROLE_CONTRIBUTOR,
    "member": ROLE_MEMBER,
}


def import_example(tree_id: str) -> None:
    """Import the Gramps example file into a tree."""
    dbmgr = WebDbManager(dirname=tree_id, create_if_missing=False)
    dbstate = dbmgr.get_db(readonly=False)
    try:
        # run_import deletes the file it imports, so import a copy
        tmp_file = os.path.join(dbmgr.path, "example.gramps")
        shutil.copy(EXAMPLE_FILE, tmp_file)
        run_import(dbstate.db, tmp_file, extension="gramps", delete=True)
    finally:
        dbstate.db.close()


def main() -> None:
    """Create the dev trees and users."""
    app = create_app()
    with app.app_context():
        # Existing trees and users are left alone, so this is safe to rerun.
        db_path = config.get("database.path")  # set by create_app
        for tree_id, name in TREES.items():
            if os.path.isdir(os.path.join(db_path, tree_id)):
                print(f"Tree '{tree_id}' exists, skipping")
                continue
            WebDbManager(dirname=tree_id, name=name, create_if_missing=True)
            if tree_id == "example":
                import_example(tree_id)
                media_dir = os.path.join(app.config["MEDIA_BASE_DIR"], tree_id)
                shutil.copytree(EXAMPLE_DIR, media_dir, dirs_exist_ok=True)

        user_db.create_all()
        users = [("admin", ROLE_ADMIN, None)]
        for tree_id in TREES:
            # example tree users keep the short names used so far
            prefix = "" if tree_id == "example" else f"{tree_id}_"
            users += [(f"{prefix}{r}", role, tree_id) for r, role in ROLES.items()]
        existing = {name for (name,) in user_db.session.query(User.name)}
        for username, role, tree_id in users:
            if username in existing:
                print(f"User '{username}' exists, skipping")
                continue
            add_user(
                username,
                username,
                fullname=username.replace("_", " ").title(),
                role=role,
                tree=tree_id,
            )


if __name__ == "__main__":
    main()
