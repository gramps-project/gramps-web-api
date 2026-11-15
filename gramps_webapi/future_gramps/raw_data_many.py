#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026       Doug Blank
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

"""Read the raw data of many people or families at once.

Backport of https://github.com/gramps-project/gramps/pull/2574 to the
Gramps version currently pinned by Gramps Web API. The functions below are
copied verbatim from the methods of that PR, with `super()` in `DBAPI`
written out, and `apply_patch` adds them to `DbReadBase`, `DbGeneric` and
`DBAPI`:

- `get_raw_person_data_many` and `get_raw_family_data_many` yield
  (handle, raw data) for the objects that are found. By default they read
  one handle at a time, so proxies keep deciding what is visible.
- `DBAPI` reads up to `RAW_DATA_BATCH_SIZE` handles in one query, unless a
  subclass changes how one object is read.

`SharedPostgreSQL` changes how one object is read, to scope it to a tree,
so it reads one handle at a time unless Gramps Web API adds a scoped batch
read, see `dbloader.py`. `RestrictedDb` has its own batch reads.

Remove this module once the pinned Gramps version contains them.
"""

from gramps.gen.db.base import DbReadBase
from gramps.gen.db.dbconst import FAMILY_KEY, KEY_TO_NAME_MAP, PERSON_KEY
from gramps.gen.db.generic import DbGeneric
from gramps.gen.errors import HandleError
from gramps.plugins.db.dbapi.dbapi import DBAPI

# The most handles read in one query, well below SQLite's limit on the
# number of parameters.
RAW_DATA_BATCH_SIZE = 500


def _raw_data_many(get_raw_data, handles):
    """
    Yield (handle, raw data) for the objects with the given handles, read
    one by one, leaving out handles that are not found.
    """
    for handle in dict.fromkeys(handles):
        try:
            data = get_raw_data(handle)
        except HandleError:
            # proxies raise this for objects that do not exist
            continue
        if data is not None:
            yield handle, data


# DbReadBase


def get_raw_person_data_many(self, handles):
    """
    Yield (handle, raw data) for the Person objects with the given
    handles, in any order. Handles that are not found are left out, and
    a repeated handle is read once.

    Reading many objects at once can take one query rather than one
    per object. Each object's data is made as it is yielded, so that
    only the objects in use are kept in memory. This default reads them
    one by one with :meth:`get_raw_person_data`.
    """
    return _raw_data_many(self.get_raw_person_data, handles)


def get_raw_family_data_many(self, handles):
    """
    Yield (handle, raw data) for the Family objects with the given
    handles, in any order. Handles that are not found are left out, and
    a repeated handle is read once.

    Reading many objects at once can take one query rather than one
    per object. Each object's data is made as it is yielded, so that
    only the objects in use are kept in memory. This default reads them
    one by one with :meth:`get_raw_family_data`.
    """
    return _raw_data_many(self.get_raw_family_data, handles)


# DbGeneric


def generic_get_raw_data_many(self, obj_key, handles):
    """
    Yield (handle, raw data) for the objects with the given handles,
    leaving out handles that are not found. Backends can read them in
    one query.
    """
    for handle in dict.fromkeys(handles):
        data = self._get_raw_data(obj_key, handle)
        if data is not None:
            yield handle, data


def generic_get_raw_person_data_many(self, handles):
    return self._get_raw_data_many(PERSON_KEY, handles)


def generic_get_raw_family_data_many(self, handles):
    return self._get_raw_data_many(FAMILY_KEY, handles)


# DBAPI


def dbapi_get_raw_data_many(self, obj_key, handles):
    if type(self)._get_raw_data is not DBAPI._get_raw_data:
        # a subclass that changes how one object is read, for example
        # to scope it, must also change how many are read
        yield from generic_get_raw_data_many(self, obj_key, handles)
        return
    table = KEY_TO_NAME_MAP[obj_key]
    handles = list(dict.fromkeys(handles))
    for start in range(0, len(handles), RAW_DATA_BATCH_SIZE):
        batch = handles[start : start + RAW_DATA_BATCH_SIZE]
        marks = ", ".join("?" * len(batch))
        self.dbapi.execute(
            f"SELECT handle, {self.serializer.data_field} FROM {table} "
            f"WHERE handle IN ({marks})",
            batch,
        )
        # all rows are fetched before yielding, so callers may query
        # the database in between
        for handle, data in self.dbapi.fetchall():
            yield handle, self.serializer.string_to_data(data)


def apply_patch() -> None:
    """Add the batch reads to the database classes that lack them."""
    methods = [
        (DbReadBase, "get_raw_person_data_many", get_raw_person_data_many),
        (DbReadBase, "get_raw_family_data_many", get_raw_family_data_many),
        (DbGeneric, "_get_raw_data_many", generic_get_raw_data_many),
        (DbGeneric, "get_raw_person_data_many", generic_get_raw_person_data_many),
        (DbGeneric, "get_raw_family_data_many", generic_get_raw_family_data_many),
        (DBAPI, "_get_raw_data_many", dbapi_get_raw_data_many),
    ]
    for cls, name, method in methods:
        # only where the class doesn't define it, e.g. in a Gramps version
        # that contains it
        if name not in vars(cls):
            setattr(cls, name, method)
