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

import logging
import os

import click
from whoosh.index import LockError

from .api.util import get_db_manager, get_search_indexer
from .app import create_app
from .auth import SQLAuth
from .const import ENV_CONFIG_FILE

logging.basicConfig()
LOG = logging.getLogger("gramps_webapi")


@click.group("cli")
@click.option("--config", help="Set the path to the config file")
@click.pass_context
def cli(ctx, config):
    """Gramps web API command line interface."""
    if config:
        os.environ[ENV_CONFIG_FILE] = os.path.abspath(config)
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
    ctx.obj["auth"] = SQLAuth(db_uri=app.config["USER_DB_URI"])


@user.command("add")
@click.argument("name")
@click.argument("password", required=True)
@click.option("--fullname", help="Full name", default="")
@click.option("--email", help="E-mail address", default=None)
@click.option("--role", help="User role", default=0, type=int)
@click.option("--tree", help="Tree ID", default=None)
@click.pass_context
def user_add(ctx, name, password, fullname, email, role, tree):
    LOG.error("Adding user {} ...".format(name))
    auth = ctx.obj["auth"]
    auth.create_table()
    auth.add_user(name, password, fullname, email, role, tree)


@user.command("delete")
@click.argument("name")
@click.pass_context
def user_del(ctx, name):
    LOG.info("Deleting user {} ...".format(name))
    auth = ctx.obj["auth"]
    auth.delete_user(name)


@cli.group("search", help="Manage the full-text search index.")
@click.option("--tree", help="Tree ID", default=None)
@click.pass_context
def search(ctx, tree):
    if not tree:
        raise ValueError("Tree ID is required.")
    app = ctx.obj["app"]
    with app.app_context():
        ctx.obj["db_manager"] = get_db_manager(tree=tree)
        ctx.obj["search_indexer"] = get_search_indexer()


@search.command("index-full")
@click.pass_context
def index_full(ctx):
    LOG.info("Rebuilding search index ...")
    app = ctx.obj["app"]
    db_manager = ctx.obj["db_manager"]
    indexer = ctx.obj["search_indexer"]
    db = db_manager.get_db().db
    try:
        indexer.reindex_full(db)
    except LockError:
        LOG.warning("Index is locked")
    except:
        LOG.exception("Error during indexing")
    finally:
        db.close()
    LOG.info("Done building search index.")


@search.command("index-incremental")
@click.pass_context
def index_incremental(ctx):
    app = ctx.obj["app"]
    db_manager = ctx.obj["db_manager"]
    indexer = ctx.obj["search_indexer"]
    db = db_manager.get_db().db
    try:
        indexer.reindex_incremental(db)
    except LockError:
        LOG.warning("Index is locked")
    except:
        LOG.exception("Error during indexing")
    finally:
        db.close()
    LOG.info("Done updating search index.")


if __name__ == "__main__":
    LOG.setLevel(logging.INFO)

    cli(
        prog_name="python3 -m gramps_webapi"
    )  # pylint:disable=no-value-for-parameter,unexpected-keyword-arg
