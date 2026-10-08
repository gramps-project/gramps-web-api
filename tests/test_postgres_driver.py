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
        ("postgresql+psycopg2://u:p@db/users", "postgresql+psycopg2://u:p@db/users"),
        ("postgresql+psycopg://u:p@db/users", "postgresql+psycopg://u:p@db/users"),
        ("sqlite://", "sqlite://"),
        ("sqlite:////app/users/users.sqlite", "sqlite:////app/users/users.sqlite"),
    ],
)
def test_pin_postgres_driver(url, expected):
    assert pin_postgres_driver(url) == expected


def test_user_db_uses_psycopg2():
    app = create_app(
        config={
            "TREE": "test",
            "SECRET_KEY": "test",
            "USER_DB_URI": "postgresql://u:p@localhost/users",
        },
        config_from_env=False,
    )
    assert (
        app.config["SQLALCHEMY_DATABASE_URI"]
        == "postgresql+psycopg2://u:p@localhost/users"
    )
    assert app.config["USER_DB_URI"] == "postgresql://u:p@localhost/users"


def test_search_metadata_uses_psycopg2():
    engine = _get_engine("postgresql://u:p@localhost/search")
    assert engine.dialect.driver == "psycopg2"
