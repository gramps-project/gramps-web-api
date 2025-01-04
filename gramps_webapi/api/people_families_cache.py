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

from typing import Generator

from gramps.gen.proxy.proxybase import ProxyDbBase
from gramps.gen.db import DbReadBase
from gramps.gen.lib import Person, Family


class CachePeopleFamiliesProxy(ProxyDbBase):
    """Proxy database class optionally caching people and families."""

    def __init__(self, db: DbReadBase) -> None:
        """Initialize the proxy database."""
        super().__init__(db)
        self.db: DbReadBase  # for type checker
        self._people_cache: dict[str, Person] = {}
        self._family_cache: dict[str, Family] = {}

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

    def find_backlink_handles(
        self, handle, include_classes=None
    ) -> Generator[tuple[str, str], None, None]:
        """
        Find all objects that hold a reference to the object handle.

        Returns an iterator over a list of (class_name, handle) tuples.

        :param handle: handle of the object to search for.
        :type handle: str database handle
        :param include_classes: list of class names to include in the results.
            Default is None which includes all classes.
        :type include_classes: list of class names

        This default implementation does a sequential scan through all
        the primary object databases and is very slow. Backends can
        override this method to provide much faster implementations that
        make use of additional capabilities of the backend.

        Note that this is a generator function, it returns a iterator for
        use in loops. If you want a list of the results use::

            result_list = list(find_backlink_handles(handle))
        """
        return self.db.find_backlink_handles(handle, include_classes)
