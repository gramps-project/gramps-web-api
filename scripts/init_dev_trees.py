"""Set up the dev container's family trees and users (multi-tree mode).

Creates two trees with fixed IDs:

- ``example``: the Gramps example tree, including its media files
- ``empty``: an empty tree

and one user per role for each tree (password = user name), plus a
tree-less admin. Uses the Gramps Python API only; never the ``gramps``
executable, which can fall back to opening the GUI.

Runs on every container start and is safe to rerun:

- Complete trees and existing users are left alone.
- A tree whose setup was interrupted is deleted and set up again.
- Data from the old single-tree dev setup (a tree named "Gramps Web", users
  ``owner`` etc. without a tree, media at the top of the media directory)
  is moved over to multi-tree mode instead of being replaced.

Expects the dev container's environment (GRAMPSWEB_TREE="*",
GRAMPS_DATABASE_PATH, GRAMPSWEB_USER_DB_URI, GRAMPSWEB_MEDIA_BASE_DIR, ...).
"""

import os
import shutil

from gramps.cli.clidbman import NAME_FILE
from gramps.gen.config import config

from gramps_webapi.api.resources.util import run_import
from gramps_webapi.app import create_app
from gramps_webapi.auth import User, add_user, modify_user, user_db
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

# Name of the single tree created by the old dev setup
LEGACY_TREE_NAME = "Gramps Web"

# Present in a tree directory while the tree is being set up
SEEDING_MARKER = ".dev_seeding"


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


def is_complete(tree_path: str) -> bool:
    """Tell whether a tree directory holds a fully set up tree.

    WebDbManager writes the name file last when creating a tree, and the
    seeding marker is only removed once the import and media copy are done.
    """
    return os.path.isfile(os.path.join(tree_path, NAME_FILE)) and not os.path.exists(
        os.path.join(tree_path, SEEDING_MARKER)
    )


def find_legacy_tree() -> str | None:
    """Return the directory name of the old single-tree setup's tree, if any."""
    try:
        return WebDbManager(name=LEGACY_TREE_NAME, create_if_missing=False).dirname
    except ValueError:
        return None


def migrate_legacy_media(media_base_dir: str, tree_id: str, db_path: str) -> None:
    """Move media files of the old single-tree setup into the tree's directory."""
    target = os.path.join(media_base_dir, tree_id)
    if os.path.exists(target) or not os.path.isdir(media_base_dir):
        return  # already migrated, or nothing to migrate
    tree_dirs = set(os.listdir(db_path))
    entries = [
        entry
        for entry in os.listdir(media_base_dir)
        # leave the media directories of other trees alone
        if not (
            entry in tree_dirs and os.path.isdir(os.path.join(media_base_dir, entry))
        )
    ]
    os.makedirs(target)
    for entry in entries:
        shutil.move(os.path.join(media_base_dir, entry), target)
    print(f"Moved {len(entries)} media files/folders to {target}")


def setup_tree(tree_id: str, name: str, db_path: str, media_base_dir: str) -> None:
    """Create one of the dev trees, unless it is already complete."""
    tree_path = os.path.join(db_path, tree_id)
    if os.path.isdir(tree_path):
        if is_complete(tree_path):
            print(f"Tree '{tree_id}' exists, skipping")
            return
        print(f"Setup of tree '{tree_id}' was interrupted, starting over")
        shutil.rmtree(tree_path)
    WebDbManager(dirname=tree_id, name=name, create_if_missing=True)
    marker = os.path.join(tree_path, SEEDING_MARKER)
    with open(marker, "w", encoding="utf8"):
        pass
    if tree_id == "example":
        import_example(tree_id)
        media_dir = os.path.join(media_base_dir, tree_id)
        shutil.copytree(EXAMPLE_DIR, media_dir, dirs_exist_ok=True)
    os.remove(marker)


def main() -> None:
    """Create the dev trees and users."""
    app = create_app()
    with app.app_context():
        db_path = config.get("database.path")  # set by create_app
        media_base_dir = app.config["MEDIA_BASE_DIR"]

        # The old single-tree setup's tree plays the part of the example tree
        legacy_tree = find_legacy_tree()
        if legacy_tree:
            print(
                f"Found tree '{LEGACY_TREE_NAME}' of the old single-tree setup, "
                "using it instead of the example tree"
            )
            migrate_legacy_media(media_base_dir, legacy_tree, db_path)

        for tree_id, name in TREES.items():
            if tree_id == "example" and legacy_tree:
                continue
            setup_tree(tree_id, name, db_path, media_base_dir)

        user_db.create_all()
        example_tree = legacy_tree or "example"
        users: list[tuple[str, int, str | None]] = [("admin", ROLE_ADMIN, None)]
        for tree_id in TREES:
            # example tree users keep the short names used so far
            prefix = "" if tree_id == "example" else f"{tree_id}_"
            target = example_tree if tree_id == "example" else tree_id
            users += [(f"{prefix}{r}", role, target) for r, role in ROLES.items()]
        existing = dict(user_db.session.query(User.name, User.tree))
        for username, role, user_tree in users:
            if username not in existing:
                add_user(
                    username,
                    username,
                    fullname=username.replace("_", " ").title(),
                    role=role,
                    tree=user_tree,
                )
            elif user_tree and not existing[username]:
                # Users of the old single-tree setup have no tree, which
                # locks them out in multi-tree mode
                modify_user(username, tree=user_tree)
                print(f"Assigned user '{username}' to tree '{user_tree}'")
            else:
                print(f"User '{username}' exists, skipping")


if __name__ == "__main__":
    main()
