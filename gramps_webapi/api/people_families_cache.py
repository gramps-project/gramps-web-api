#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025       David Straub
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


"""A proxy database class optionally caching people and families."""

from gramps.gen.proxy.proxybase import ProxyDbBase
from gramps.gen.db import DbReadBase
from gramps.gen.lib import Person, Family


class CachePeopleFamiliesProxy(ProxyDbBase):
    """Proxy database class optionally caching people and families."""

    def __init__(self, db: DbReadBase) -> None:
        """Initialize the proxy database."""
        super().__init__(db)
        self.db: DbReadBase  # for type checker
        self._people_cache = {}
        self._family_cache = {}

    def cache_people(self) -> None:
        """Cache all people."""
        self._people_cache = {obj.handle: obj for obj in self.db.iter_people()}

    def cache_families(self) -> None:
        """Cache all families."""
        self._family_cache = {obj.handle: obj for obj in self.db.iter_families()}

    def get_person_from_handle(self, handle: str) -> Person:
        """Get a person from the cache or the database."""
        if handle in self._people_cache:
            return self._people_cache[handle]
        return self.db.get_person_from_handle(handle)

    def get_family_from_handle(self, handle: str) -> Family:
        """Get a family from the cache or the database."""
        if handle in self._family_cache:
            return self._family_cache[handle]
        return self.db.get_family_from_handle(handle)
