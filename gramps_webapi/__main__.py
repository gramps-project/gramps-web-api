#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Command line interface for the Gramps web API."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
import warnings

import click

from .api.search import get_search_indexer
from .api.util import get_db_manager, list_trees, close_db
from .app import create_app
from .auth import add_user, delete_user, fill_tree, user_db
from .const import ENV_CONFIG_FILE, TREE_MULTI
from .dbmanager import WebDbManager

logging.basicConfig()
LOG = logging.getLogger("gramps_webapi")


@click.group("cli")
@click.option("--config", help="Set the path to the config file")
@click.pass_context
def cli(ctx, config):
    """Gramps web API command line interface."""
    if config:
        os.environ[ENV_CONFIG_FILE] = os.path.abspath(config)
    # suppress flask-limiter warning
    warnings.filterwarnings(
        "ignore",
        message=".*https://flask-limiter.readthedocs.io#configuring-a-storage-backend.*",
    )
    ctx.obj = {"app": create_app()}


@cli.command("run")
@click.option("-p", "--port", help="Port to use (default: 5000)", default=5000)
@click.option("--tree", help="Tree ID", default=None)
@click.pass_context
def run(ctx, port, tree):
    """Run the app."""
    app = ctx.obj["app"]
    app.run(port=port, threaded=True)


@cli.group("user", help="Manage users.")
@click.pass_context
def user(ctx):
    app = ctx.obj["app"]


@user.command("add")
@click.argument("name")
@click.argument("password", required=True)
@click.option("--fullname", help="Full name", default="")
@click.option("--email", help="E-mail address", default=None)
@click.option("--role", help="User role", default=0, type=int)
@click.option("--tree", help="Tree ID", default=None)
@click.pass_context
def user_add(ctx, name, password, fullname, email, role, tree):
    """Add a user."""
    LOG.error(f"Adding user {name} ...")
    app = ctx.obj["app"]
    with app.app_context():
        user_db.create_all()
        add_user(name, password, fullname, email, role, tree)


@user.command("delete")
@click.argument("name")
@click.pass_context
def user_del(ctx, name):
    """Delete a user."""
    LOG.info(f"Deleting user {name} ...")
    app = ctx.obj["app"]
    with app.app_context():
        delete_user(name)


@user.command("fill-tree")
@click.argument("tree")
@click.pass_context
def cmd_fill_tree(ctx, tree):
    """Set the Tree ID for users where it is missing."""
    app = ctx.obj["app"]
    with app.app_context():
        fill_tree(tree)


@user.command("migrate")
@click.pass_context
def migrate_db(ctx):
    """Upgrade the user database schema, if required."""
    app = ctx.obj["app"]
    cmd = [sys.executable, "-m", "alembic", "upgrade", "head"]
    env = os.environ.copy()
    env["GRAMPSWEB_USER_DB_URI"] = app.config["USER_DB_URI"]
    subprocess.run(cmd, env=env, check=True)


@cli.group("search", help="Manage the full-text search index.")
@click.option("--tree", help="Tree ID", default=None)
@click.option(
    "--semantic/--fulltext",
    help="Semantic rather than full-text search index",
    default=False,
)
@click.pass_context
def search(ctx, tree, semantic):
    app = ctx.obj["app"]
    if not tree:
        if app.config["TREE"] == TREE_MULTI:
            raise ValueError("`tree` is required when multi-tree support is enabled.")
        # needed for backwards compatibility!
        dbmgr = WebDbManager(
            name=app.config["TREE"],
            create_if_missing=False,
            ignore_lock=app.config["IGNORE_DB_LOCK"],
        )
        tree = dbmgr.dirname
    with app.app_context():
        ctx.obj["db_manager"] = get_db_manager(tree=tree)
        ctx.obj["search_indexer"] = get_search_indexer(tree=tree, semantic=semantic)


def progress_callback_count(current: int, total: int, prev: int | None = None) -> None:
    if total == 0:
        return
    pct = int(100 * current / total)
    if prev is None:
        prev = current - 1
    pct_prev = int(100 * prev / total)
    if current == 0 or pct != pct_prev:
        LOG.info(f"Progress: {pct}%")


@search.command("index-full")
@click.pass_context
def index_full(ctx):
    """Perform a full reindex."""
    LOG.info("Rebuilding search index ...")
    db_manager = ctx.obj["db_manager"]
    indexer = ctx.obj["search_indexer"]
    db = db_manager.get_db().db

    t0 = time.time()
    try:
        indexer.reindex_full(db, progress_cb=progress_callback_count)
    except:
        LOG.exception("Error during indexing")
    finally:
        close_db(db)
    LOG.info(f"Done building search index in {time.time() - t0:.0f} seconds.")


@search.command("index-incremental")
@click.pass_context
def index_incremental(ctx):
    """Perform an incremental reindex."""
    db_manager = ctx.obj["db_manager"]
    indexer = ctx.obj["search_indexer"]
    db = db_manager.get_db().db

    try:
        indexer.reindex_incremental(db, progress_cb=progress_callback_count)
    except Exception:
        LOG.exception("Error during indexing")
    finally:
        close_db(db)
    LOG.info("Done updating search index.")


@cli.group("tree", help="Manage trees.")
@click.pass_context
def tree(ctx):
    pass


@tree.command("list")
@click.pass_context
def tree_list(ctx):
    """List existing trees and their IDs."""
    tree_details = list_trees()
    print(f"{'Tree ID':>36}  {'Name':<}")
    for details in tree_details:
        name = details[0]
        path = details[1]
        dirname = os.path.basename(path)
        print(f"{dirname:>36}  {name:<}")


@cli.group("grampsdb", help="Manage a Gramps daabase.")
@click.option("--tree", help="Tree ID", default=None)
@click.pass_context
def grampsdb(ctx, tree):
    app = ctx.obj["app"]
    if not tree:
        if app.config["TREE"] == TREE_MULTI:
            raise ValueError("`tree` is required when multi-tree support is enabled.")
        # needed for backwards compatibility!
        dbmgr = WebDbManager(name=app.config["TREE"], create_if_missing=False)
        tree = dbmgr.dirname
    with app.app_context():
        ctx.obj["db_manager"] = get_db_manager(tree=tree)


@grampsdb.command("migrate")
@click.pass_context
def migrate_gramps_db(ctx):
    """Upgrade the Gramps database schema, if required."""
    dbmgr = ctx.obj["db_manager"]
    dbmgr.upgrade_if_needed()


if __name__ == "__main__":
    LOG.setLevel(logging.INFO)

    cli(
        prog_name="python3 -m gramps_webapi"
    )  # pylint:disable=no-value-for-parameter,unexpected-keyword-arg
