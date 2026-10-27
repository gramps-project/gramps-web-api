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

"""A read-only database that only returns what an access policy allows.

`RestrictedDb` is not a Gramps proxy: it has no `db` attribute, so Gramps
code that unwraps proxies (e.g. `probably_alive`) can't reach the base
database through it. It implements only the methods Gramps Web API needs;
all other `DbReadBase` methods raise `NotImplementedError`.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from functools import partial
from typing import (
    Callable,
    ContextManager,
    Generator,
    Iterator,
    NoReturn,
    Optional,
    Union,
)

from gramps.gen.db import DbReadBase
from gramps.gen.db.bookmarks import DbBookmarks
from gramps.gen.db.dbconst import CLASS_TO_KEY_MAP, KEY_TO_CLASS_MAP, KEY_TO_NAME_MAP
from gramps.gen.db.generic import Cursor
from gramps.gen.errors import HandleError
from gramps.gen.lib import Researcher, Tag
from gramps.gen.lib.primaryobj import PrimaryObject
from gramps.gen.utils.grampslocale import GrampsLocale
from gramps.gen.lib.json_utils import (
    DataDict,
    data_to_object,
    remove_object,
    string_to_data,
)

from ..resources.db_backend import (
    has_secondary_columns,
    sql_count,
    sql_sorted_handles,
)
from .policy import AccessPolicy
from .sanitize import (
    LINK_PREFIX,
    RawData,
    as_handle,
    as_list,
    as_object,
    note_links,
    sanitize,
)

# primary object classes with privacy, by class name
CLASS_NAMES = [
    "Person",
    "Family",
    "Event",
    "Place",
    "Source",
    "Citation",
    "Media",
    "Repository",
    "Note",
]
# table names, also used in method names (`get_person_from_handle`, ...)
TABLES = {name: KEY_TO_NAME_MAP[CLASS_TO_KEY_MAP[name]] for name in CLASS_NAMES}
# `iter_people`, `iter_families`, ...
ITER_NAMES = {
    "Person": "people",
    "Family": "families",
    "Event": "events",
    "Place": "places",
    "Source": "sources",
    "Citation": "citations",
    "Media": "media",
    "Repository": "repositories",
    "Note": "notes",
}


# (handle, extra column) of an object that is visible on its own
Row = tuple[str, Optional[str]]
# Columns needed besides the handle to decide whether an object is visible.
EXTRA_COLUMNS = {
    "Citation": "source_handle",
    # only the data of notes that may contain links
    "Note": "CASE WHEN json_data LIKE ? THEN json_data END",
}
# Lookups of single handles in a table, after which all visible handles of the
# table are read at once.
SINGLE_LOOKUPS = 200

CUSTOM_TYPE_METHODS = [
    "get_child_reference_types",
    "get_event_attribute_types",
    "get_event_roles",
    "get_event_types",
    "get_family_attribute_types",
    "get_family_event_types",
    "get_family_relation_types",
    "get_media_attribute_types",
    "get_name_types",
    "get_note_types",
    "get_origin_types",
    "get_person_attribute_types",
    "get_person_event_types",
    "get_place_types",
    "get_repository_types",
    "get_source_attribute_types",
    "get_source_media_types",
    "get_url_types",
]


class RestrictedDb(DbReadBase):
    """Read-only access to a tree, restricted by an access policy."""

    def __init__(self, db: DbReadBase, policy: AccessPolicy) -> None:
        """Wrap the base database `db`."""
        super().__init__()
        # name-mangled, so that code looking for `db` or `basedb` finds
        # nothing to unwrap
        self.__db = db
        self.__policy = policy
        # class name -> all visible handles
        self.__visible: dict[str, frozenset[str]] = {}
        # class name -> handle -> visible, for single lookups
        self.__single: dict[str, dict[str, bool]] = {}
        # family handle -> handles of children with a public child reference,
        # read at once when iterating over all people
        self.__child_refs: Optional[dict[str, frozenset[str]]] = None
        # the same for single families, until a request needs many
        self.__single_child_refs: dict[str, frozenset[str]] = {}
        self.name_formats = db.name_formats
        # the tree's title, set by Gramps when opening it
        self.db_name = getattr(db, "db_name", "")
        for name in (
            "bookmarks",
            "family_bookmarks",
            "event_bookmarks",
            "place_bookmarks",
            "source_bookmarks",
            "citation_bookmarks",
            "repo_bookmarks",
            "media_bookmarks",
            "note_bookmarks",
        ):
            setattr(self, name, self.__restrict_bookmarks(getattr(db, name), name))
        for class_name in CLASS_NAMES:
            self.__add_methods(class_name)
        # Custom types are collected from all objects, private or not, as by
        # the private proxy before (see KNOWN_LEAKS in the privacy canary).
        for name in CUSTOM_TYPE_METHODS:
            setattr(self, name, getattr(db, name))

    @property
    def policy(self) -> AccessPolicy:
        """The access policy applied by this database."""
        return self.__policy

    # visibility

    def is_visible(self, class_name: str, handle: Optional[str]) -> bool:
        """Whether the object with this handle exists and is visible."""
        if class_name == "Tag":
            # tags have no privacy
            return True
        if not handle:
            return False
        visible = self.__visible.get(class_name)
        if visible is not None:
            return handle in visible
        # Look up single handles until a request needs many: reading all
        # visible handles of a large table costs more than a few lookups.
        cache = self.__single.setdefault(class_name, {})
        if handle in cache:
            return cache[handle]
        if len(cache) >= SINGLE_LOOKUPS:
            return handle in self.__visible_handles(class_name)
        rows = self.__select_visible(class_name, EXTRA_COLUMNS.get(class_name), handle)
        cache[handle] = bool(rows) and self.__row_visible(class_name, rows[0])
        return cache[handle]

    def __visible_handles(self, class_name: str) -> frozenset[str]:
        if class_name not in self.__visible:
            self.__visible[class_name] = frozenset(
                row[0]
                for row in self.__select_visible(
                    class_name, EXTRA_COLUMNS.get(class_name)
                )
                if self.__row_visible(class_name, row)
            )
        return self.__visible[class_name]

    def __row_visible(self, class_name: str, row: Row) -> bool:
        """Whether an object that is visible on its own is visible.

        `row` is (handle, extra column), see `EXTRA_COLUMNS`.
        """
        if class_name == "Citation":
            # a citation of a source that isn't visible is hidden, since
            # Gramps' private proxy hides references to it
            source_handle = row[1]
            return not source_handle or self.is_visible("Source", source_handle)
        if class_name == "Note":
            # a note linking to an object that isn't visible is hidden
            json_data = row[1]
            return json_data is None or self.__links_visible(string_to_data(json_data))
        return True

    def __select_visible(
        self,
        class_name: str,
        column: Optional[str] = None,
        handle: Optional[str] = None,
    ) -> list[Row]:
        """Return (handle, column) rows of objects that are visible on their own.

        Filters on the `private` secondary column, and on the handle if given.
        Without a column, the second value is None.
        """
        db = self.__db
        if not has_secondary_columns(db):
            return list(self.__select_visible_python(class_name, column, handle))
        sql = (
            f"SELECT handle, {column or 'NULL'} FROM {TABLES[class_name]} "
            f"WHERE {self.__policy.sql_condition()}"
        )
        params: list[Union[str, int]] = (
            [f"%{LINK_PREFIX}%"] if column and "?" in column else []
        )
        if handle is not None:
            sql += " AND handle = ?"
            params.append(handle)
        treeid = getattr(db.dbapi, "treeid", None)
        if treeid is not None:
            sql += " AND treeid = ?"
            params.append(treeid)
        db.dbapi.execute(sql, params)
        return db.dbapi.fetchall()

    def __select_visible_python(
        self, class_name: str, column: Optional[str], handle: Optional[str]
    ) -> Iterator[Row]:
        """Like `__select_visible`, for backends without SQL."""
        key = CLASS_TO_KEY_MAP[class_name]
        if handle is None:
            items = self.__db._iter_raw_data(key)
        else:
            data = self.__db._get_raw_data(key, handle)
            items = [] if data is None else [(handle, data)]
        for item_handle, data in items:
            if not self.__policy.is_visible(data):
                continue
            if not column:
                yield item_handle, None
            elif class_name == "Citation":
                yield item_handle, as_handle(data.get("source_handle"))
            else:
                text = json.dumps(remove_object(data))
                yield item_handle, text if LINK_PREFIX in text else None

    def __links_visible(self, data: RawData) -> bool:
        for class_name, key, link_value in note_links(data):
            value: Optional[str] = link_value
            if class_name not in TABLES:
                continue
            if key == "gramps_id":
                target = self.__db._get_raw_from_id_data(
                    CLASS_TO_KEY_MAP[class_name], value
                )
                value = as_handle(target["handle"]) if target else None
            if class_name == "Note":
                # only the note's own privacy, to avoid cycles
                visible = bool(value) and bool(
                    self.__select_visible("Note", handle=value)
                )
            else:
                visible = self.is_visible(class_name, value)
            if not visible:
                return False
        return True

    def get_sorted_handles(
        self,
        class_name: str,
        order: list[tuple[str, bool]],
        locale: Optional[GrampsLocale] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> Optional[tuple[list[str], int]]:
        """Return a page of visible handles sorted in SQL, and their total number.

        `order` is a list of (column, descending), most significant first, see
        `db_backend.sql_sorted_handles`. Without `limit`, all handles are
        returned. Return None if the backend can't sort this in SQL.
        """
        if not has_secondary_columns(self.__db):
            return None
        if class_name == "Tag":
            # tags have no privacy
            table, condition = "tag", "1 = 1"
        elif class_name in TABLES:
            table, condition = TABLES[class_name], self.__policy.sql_condition()
        else:
            return None
        if class_name in EXTRA_COLUMNS and not self.__policy.sees_everything:
            # visibility isn't decided by the private column alone, so page
            # after filtering
            handles = sql_sorted_handles(self.__db, table, order, condition, locale)
            if handles is None:
                return None
            visible = self.__visible_handles(class_name)
            handles = [handle for handle in handles if handle in visible]
            end = None if limit is None else offset + limit
            return handles[offset:end], len(handles)
        handles = sql_sorted_handles(
            self.__db, table, order, condition, locale, limit, offset
        )
        if handles is None:
            return None
        if limit is None and offset == 0:
            return handles, len(handles)
        return handles, sql_count(self.__db, table, condition)

    # raw data and objects

    def __sanitize(self, class_name: str, data: RawData) -> DataDict:
        if self.__policy.sees_everything:
            # nothing to hide
            return DataDict(data)
        clean = sanitize(data, self.is_visible)
        if class_name == "Person":
            person_handle = as_handle(data["handle"]) or ""
            clean["parent_family_list"] = [
                handle
                for handle in as_list(clean["parent_family_list"])
                if self.__child_ref_visible(as_handle(handle) or "", person_handle)
            ]
        return DataDict(clean)

    def __child_ref_visible(self, family_handle: str, person_handle: str) -> bool:
        """Whether the family's reference to the child isn't private."""
        cache = self.__single_child_refs
        if self.__child_refs is None and family_handle not in cache:
            if len(cache) >= SINGLE_LOOKUPS:
                self.__load_child_refs()
            else:
                family = self.__db._get_raw_data(
                    CLASS_TO_KEY_MAP["Family"], family_handle
                )
                cache[family_handle] = (
                    frozenset() if family is None else _public_children(family)
                )
        if self.__child_refs is not None:
            return person_handle in self.__child_refs.get(family_handle, ())
        return person_handle in cache[family_handle]

    def __load_child_refs(self) -> None:
        """Read the public child references of all families at once."""
        if self.__child_refs is None:
            self.__child_refs = {
                handle: _public_children(data)
                for handle, data in self.__db._iter_raw_data(CLASS_TO_KEY_MAP["Family"])
            }

    def __get_raw(self, class_name: str, handle: Optional[str]) -> Optional[DataDict]:
        if not self.is_visible(class_name, handle):
            return None
        data = self.__db._get_raw_data(CLASS_TO_KEY_MAP[class_name], handle)
        if data is None:
            return None
        return self.__sanitize(class_name, data)

    def __get_object(
        self, class_name: str, handle: Optional[str]
    ) -> Optional[PrimaryObject]:
        """Like the base database: HandleError if missing, None if hidden."""
        if handle is None:
            raise HandleError("Handle is None")
        if not handle:
            raise HandleError("Handle is empty")
        data = self.__get_raw(class_name, handle)
        if data is not None:
            return data_to_object(data)
        if self.__db._get_raw_data(CLASS_TO_KEY_MAP[class_name], handle) is None:
            raise HandleError(f"Handle {handle} not found")
        return None

    def __get_raw_from_id(self, class_name: str, gramps_id: str) -> Optional[DataDict]:
        data = self.__db._get_raw_from_id_data(CLASS_TO_KEY_MAP[class_name], gramps_id)
        if data is None or not self.is_visible(class_name, as_handle(data["handle"])):
            return None
        return self.__sanitize(class_name, data)

    def __get_object_from_id(
        self, class_name: str, gramps_id: str
    ) -> Optional[PrimaryObject]:
        data = self.__get_raw_from_id(class_name, gramps_id)
        return None if data is None else data_to_object(data)

    def __iter_raw(self, class_name: str) -> Iterator[tuple[str, DataDict]]:
        visible = self.__visible_handles(class_name)
        if class_name == "Person":
            self.__load_child_refs()
        for handle, data in self.__db._iter_raw_data(CLASS_TO_KEY_MAP[class_name]):
            if handle in visible:
                yield handle, self.__sanitize(class_name, data)

    def __iter_objects(self, class_name: str) -> Iterator[PrimaryObject]:
        for _, data in self.__iter_raw(class_name):
            yield data_to_object(data)

    def __iter_handles(self, class_name: str) -> Iterator[str]:
        visible = self.__visible_handles(class_name)
        for handle in self.__db.method("iter_%s_handles", TABLES[class_name])():
            if handle in visible:
                yield handle

    def __get_handles(
        self,
        class_name: str,
        sort_handles: bool = False,
        locale: Optional[GrampsLocale] = None,
    ) -> list[str]:
        """Return the visible handles, unsorted."""
        if sort_handles:
            # the base database would sort by values that may be hidden
            raise NotImplementedError("Sorted handles are not supported")
        visible = self.__visible_handles(class_name)
        get_handles = self.__db.method("get_%s_handles", TABLES[class_name])
        return [handle for handle in get_handles() if handle in visible]

    def __add_methods(self, class_name: str) -> None:
        """Add the per-class methods, e.g. `get_person_from_handle`."""
        table = TABLES[class_name]
        methods = {
            f"get_{table}_from_handle": partial(self.__get_object, class_name),
            f"get_{table}_from_gramps_id": partial(
                self.__get_object_from_id, class_name
            ),
            f"get_raw_{table}_data": partial(self.__get_raw, class_name),
            f"_get_raw_{table}_from_id_data": partial(
                self.__get_raw_from_id, class_name
            ),
            f"_iter_raw_{table}_data": partial(self.__iter_raw, class_name),
            f"get_{table}_cursor": lambda: Cursor(partial(self.__iter_raw, class_name)),
            f"has_{table}_handle": partial(self.is_visible, class_name),
            f"iter_{table}_handles": partial(self.__iter_handles, class_name),
            f"get_{table}_handles": partial(self.__get_handles, class_name),
            f"iter_{ITER_NAMES[class_name]}": partial(self.__iter_objects, class_name),
            f"get_number_of_{ITER_NAMES[class_name]}": lambda: len(
                self.__visible_handles(class_name)
            ),
        }
        if class_name == "Media":
            # Gramps' name for `has_media_handle`
            methods["has_object_handle"] = methods["has_media_handle"]
        for name, method in methods.items():
            setattr(self, name, method)

    def _get_raw_data(self, obj_key: int, handle: str) -> Optional[RawData]:
        """Return the sanitized raw data of a visible object, else None."""
        class_name = KEY_TO_CLASS_MAP.get(obj_key)
        if class_name == "Tag":
            return self.__db._get_raw_data(obj_key, handle)
        return self.__get_raw(class_name, handle)

    def _iter_raw_data(self, obj_key: int) -> Iterator[tuple[str, RawData]]:
        """Iterate over the sanitized raw data of visible objects."""
        class_name = KEY_TO_CLASS_MAP.get(obj_key)
        if class_name == "Tag":
            return self.__db._iter_raw_data(obj_key)
        return self.__iter_raw(class_name)

    def _get_raw_from_id_data(self, obj_key: int, gramps_id: str) -> Optional[RawData]:
        """Return the sanitized raw data of a visible object, else None."""
        return self.__get_raw_from_id(KEY_TO_CLASS_MAP[obj_key], gramps_id)

    # references

    def find_backlink_handles(
        self, handle: str, include_classes: Optional[list[str]] = None
    ) -> Iterator[tuple[str, str]]:
        """Find visible objects that reference the handle after sanitizing.

        This also skips objects that only reference the handle through
        something hidden, e.g. a private media reference.
        """
        for class_name, ref_handle in self.__db.find_backlink_handles(
            handle, include_classes
        ):
            if class_name not in TABLES:
                # tags
                yield class_name, ref_handle
                continue
            data = self.__get_raw(class_name, ref_handle)
            if data is None:
                continue
            obj = data_to_object(data)
            if any(
                ref == handle for _, ref in obj.get_referenced_handles_recursively()
            ):
                yield class_name, ref_handle

    # people

    def get_default_handle(self) -> Optional[str]:
        """Return the home person's handle, if visible."""
        handle = self.__db.get_default_handle()
        if handle and self.is_visible("Person", handle):
            return handle
        return None

    def get_default_person(self) -> Optional[PrimaryObject]:
        """Return the home person, if visible."""
        handle = self.get_default_handle()
        return self.get_person_from_handle(handle) if handle else None

    def get_surname_list(self) -> list[str]:
        """Return the sorted surnames of people whose primary name is visible."""
        if self.__policy.sees_everything:
            return self.__db.get_surname_list()
        visible = set()
        people = self.__visible_handles("Person")
        # no need to sanitize: only the primary name is used
        for handle, data in self.__db._iter_raw_data(CLASS_TO_KEY_MAP["Person"]):
            if handle not in people:
                continue
            name = as_object(data["primary_name"])
            if name.get("private"):
                continue
            # like Gramps' list, the first surname, not the one flagged primary
            surnames = as_list(name["surname_list"])
            visible.add(as_object(surnames[0])["surname"] if surnames else "")
        return [s for s in self.__db.get_surname_list() if s in visible]

    # metadata that doesn't depend on privacy

    def get_dbname(self) -> str:
        """Return the name of the tree."""
        return self.__db.get_dbname()

    def get_dbid(self) -> str:
        """Return the ID of the tree."""
        return self.__db.get_dbid()

    def get_summary(self) -> dict[str, str]:
        """Return a dictionary of summary items."""
        return self.__db.get_summary()

    def get_researcher(self) -> Researcher:
        """Return the researcher (tree owner) information."""
        return self.__db.get_researcher()

    def get_mediapath(self) -> Optional[str]:
        """Return the base path of media files."""
        return self.__db.get_mediapath()

    def get_save_path(self) -> str:
        """Return the path of the database directory."""
        return self.__db.get_save_path()

    def get_schema_version(self) -> int:
        """Return the database schema version."""
        return self.__db.get_schema_version()

    def get_name_group_mapping(self, surname: str) -> str:
        """Return the group a surname belongs to."""
        return self.__db.get_name_group_mapping(surname)

    def get_name_group_keys(self) -> list[str]:
        """Return the surnames that have a group."""
        return self.__db.get_name_group_keys()

    # tags have no privacy

    def get_tag_from_handle(self, handle: str) -> Tag:
        """Return a tag."""
        return self.__db.get_tag_from_handle(handle)

    def get_tag_from_name(self, name: str) -> Optional[Tag]:
        """Return a tag by name."""
        return self.__db.get_tag_from_name(name)

    def get_tag_handles(
        self, *args: Union[bool, GrampsLocale], **kwargs: Union[bool, GrampsLocale]
    ) -> list[str]:
        """Return all tag handles."""
        return self.__db.get_tag_handles(*args, **kwargs)

    def iter_tag_handles(self) -> Iterator[str]:
        """Iterate over all tag handles."""
        return self.__db.iter_tag_handles()

    def iter_tags(self) -> Iterator[Tag]:
        """Iterate over all tags."""
        return self.__db.iter_tags()

    def get_number_of_tags(self) -> int:
        """Return the number of tags."""
        return self.__db.get_number_of_tags()

    def get_raw_tag_data(self, handle: str) -> Optional[RawData]:
        """Return the raw data of a tag."""
        return self.__db.get_raw_tag_data(handle)

    def has_tag_handle(self, handle: str) -> bool:
        """Whether a tag with this handle exists."""
        return self.__db.has_tag_handle(handle)

    # bookmarks

    def __restrict_bookmarks(self, bookmarks: DbBookmarks, name: str) -> DbBookmarks:
        class_name = {
            "bookmarks": "Person",
            "family_bookmarks": "Family",
            "event_bookmarks": "Event",
            "place_bookmarks": "Place",
            "source_bookmarks": "Source",
            "citation_bookmarks": "Citation",
            "repo_bookmarks": "Repository",
            "media_bookmarks": "Media",
            "note_bookmarks": "Note",
        }[name]
        return _RestrictedBookmarks(bookmarks, partial(self.is_visible, class_name))

    def get_bookmarks(self) -> DbBookmarks:
        """Return the person bookmarks."""
        return self.bookmarks

    def get_family_bookmarks(self) -> DbBookmarks:
        """Return the family bookmarks."""
        return self.family_bookmarks

    def get_event_bookmarks(self) -> DbBookmarks:
        """Return the event bookmarks."""
        return self.event_bookmarks

    def get_place_bookmarks(self) -> DbBookmarks:
        """Return the place bookmarks."""
        return self.place_bookmarks

    def get_source_bookmarks(self) -> DbBookmarks:
        """Return the source bookmarks."""
        return self.source_bookmarks

    def get_citation_bookmarks(self) -> DbBookmarks:
        """Return the citation bookmarks."""
        return self.citation_bookmarks

    def get_repo_bookmarks(self) -> DbBookmarks:
        """Return the repository bookmarks."""
        return self.repo_bookmarks

    def get_media_bookmarks(self) -> DbBookmarks:
        """Return the media bookmarks."""
        return self.media_bookmarks

    def get_note_bookmarks(self) -> DbBookmarks:
        """Return the note bookmarks."""
        return self.note_bookmarks

    # lifecycle

    @contextmanager
    def restricted_context(
        self, context: Callable[[DbReadBase], ContextManager[DbReadBase]]
    ) -> Generator[RestrictedDb, None, None]:
        """Apply a context manager to the base database and restrict the result.

        Used to read from a snapshot (`snapshot.consistent_read`) with the
        same policy.
        """
        with context(self.__db) as db:
            yield self if db is self.__db else RestrictedDb(db, self.__policy)

    def is_open(self) -> bool:
        """Whether the base database is open."""
        return self.__db.is_open()

    def close(self) -> None:
        """Close the base database and its undo log."""
        self.__db.close()
        self.__db.undodb.close()


def _public_children(family: RawData) -> frozenset[str]:
    """Handles of the children whose reference in the family isn't private."""
    refs = [as_object(ref) for ref in as_list(family["child_ref_list"])]
    return frozenset(
        handle
        for ref in refs
        if not ref.get("private") and (handle := as_handle(ref["ref"]))
    )


class _RestrictedBookmarks(DbBookmarks):
    """Bookmarks with only visible objects, read-only."""

    def __init__(
        self, bookmarks: DbBookmarks, is_visible: Callable[[Optional[str]], bool]
    ) -> None:
        super().__init__()
        self._source = bookmarks
        self._is_visible = is_visible

    def get(self) -> list[str]:
        """Return the visible bookmarks."""
        return [handle for handle in self._source.get() if self._is_visible(handle)]

    def load(self, new_list: list[str]) -> NoReturn:
        raise NotImplementedError

    def set(self, new_list: list[str]) -> NoReturn:
        raise NotImplementedError

    def append(self, item: str) -> NoReturn:
        raise NotImplementedError

    def append_list(self, item_list: list[str]) -> NoReturn:
        raise NotImplementedError

    def remove(self, item: str) -> NoReturn:
        raise NotImplementedError

    def insert(self, pos: int, item: str) -> NoReturn:
        raise NotImplementedError

    def pop(self, item: int) -> NoReturn:
        raise NotImplementedError
