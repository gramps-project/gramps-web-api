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
    ctx.obj = create_app()


@cli.command("run")
@click.option("-p", "--port", help="Port to use (default: 5000)", default=5000)
@click.pass_context
def run(ctx, port):
    """Run the app."""
    app = ctx.obj
    app.run(port=port, threaded=True)


@cli.group("user", help="Manage users.")
@click.pass_context
def user(ctx):
    app = ctx.obj
    ctx.obj = SQLAuth(db_uri=app.config["USER_DB_URI"])


@user.command("add")
@click.argument("name")
@click.argument("password")
@click.option("--fullname", help="Full name", default="")
@click.option("--email", help="E-mail address", default=None)
@click.option("--role", help="User role", default=0, type=int)
@click.pass_context
def user_add(ctx, name, password, fullname, email, role):
    LOG.info("Adding user {} ...".format(name))
    auth = ctx.obj
    auth.create_table()
    auth.add_user(name, password, fullname, email, role)


@user.command("delete")
@click.argument("name")
@click.pass_context
def user_del(ctx, name):
    LOG.info("Deleting user {} ...".format(name))
    auth = ctx.obj
    auth.delete_user(name)


@cli.group("search", help="Manage the full-text search index.")
@click.pass_context
def search(ctx):
    pass


@search.command("index-full")
@click.pass_context
def index_full(ctx):
    LOG.info("Rebuilding search index ...")
    app = ctx.obj
    indexer = app.config["SEARCH_INDEXER"]
    db = app.config["DB_MANAGER"].get_db().db
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
    LOG.info("Updating search index ...")
    app = ctx.obj
    indexer = app.config["SEARCH_INDEXER"]
    db = app.config["DB_MANAGER"].get_db().db
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
