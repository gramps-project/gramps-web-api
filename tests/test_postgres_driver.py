#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Gramps Web contributors
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

"""Tests for pinning the PostgreSQL driver to psycopg2."""

import pytest
from sqlalchemy.engine import make_url

from gramps_webapi.api.search.metadata import _get_engine
from gramps_webapi.app import create_app
from gramps_webapi.util import pin_postgres_driver


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "postgresql://user:p%40ss@db:5432/users",
            "postgresql+psycopg2://user:p%40ss@db:5432/users",
        ),
        ("postgresql://db/users", "postgresql+psycopg2://db/users"),
        (
            "postgresql://u:p@/users?host=/var/run/postgresql",
            "postgresql+psycopg2://u:p@/users?host=/var/run/postgresql",
        ),
        ("PostgreSQL://u:p@db/users", "postgresql+psycopg2://u:p@db/users"),
        (" postgresql://u:p@db/users\n", "postgresql+psycopg2://u:p@db/users"),
    ],
)
def test_driverless_url_is_pinned(url, expected):
    assert make_url(pin_postgres_driver(url)) == make_url(expected)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg2://u:p@db/users",
        "postgresql+psycopg://u:p@db/users",
        "sqlite://",
        "sqlite:////app/users/users.sqlite",
        "not a url",
    ],
)
def test_other_url_is_left_alone(url):
    assert pin_postgres_driver(url) == url


def test_user_db_uses_psycopg2():
    app = create_app(
        config={
            "TREE": "test",
            "SECRET_KEY": "test",
            "USER_DB_URI": "postgresql://u:p@localhost/users",
        },
        config_from_env=False,
    )
    pinned = "postgresql+psycopg2://u:p@localhost/users"
    assert app.config["USER_DB_URI"] == pinned
    assert app.config["SQLALCHEMY_DATABASE_URI"] == pinned


def test_search_metadata_uses_psycopg2():
    engine = _get_engine("postgresql://u:p@localhost/search")
    assert engine.dialect.driver == "psycopg2"
