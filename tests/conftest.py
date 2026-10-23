#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

"""Pytest configuration."""

import pytest


@pytest.fixture(autouse=True, scope="module")
def clear_dbmanager_caches():
    """Start each test module with empty process-wide tree metadata caches.

    Tests remove trees directly with Gramps, which the caches don't notice,
    and Gramps can give a new tree the directory name of a removed one.
    """
    # imported here so that tests/__init__.py has set up GRAMPSHOME first
    from gramps_webapi.dbmanager import clear_caches

    clear_caches()
