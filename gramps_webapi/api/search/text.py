#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2026      David Straub
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

"""Functions for converting Gramps objects to rows of the search index.

Every row describes the object it was made from: its own text, the name
of a person, and the references a family or person holds to the people and
events it is connected to. Text of other objects is never copied, so a row
only goes stale when its own object changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Generator, Optional, Sequence

from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib import Family, Name, Person
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from unidecode import unidecode

from ...const import GRAMPS_OBJECT_PLURAL, PRIMARY_GRAMPS_OBJECTS

# document kinds
KIND_OWN = "own"  # the object's own text
KIND_NAME = "name"  # a person's primary name, found through families and events

# document variants
VARIANT_ALL = "all"  # the same for everyone
VARIANT_FULL = "full"  # including private child objects
VARIANT_REDACTED = "redacted"  # without private child objects

# reference kinds
REF_PARENT = "parent"  # family -> father or mother
REF_PARTICIPANT = "participant"  # person or family -> event

# runs of letters and digits; everything else separates tokens
_TOKEN = re.compile(r"[^\W_]+")


def tokenize(string: str) -> list[str]:
    """Split text into lowercase tokens.

    Indexed text and queries are tokenized here rather than by the database,
    so that SQLite and PostgreSQL agree: PostgreSQL's parser would otherwise
    keep e.g. `scanned_microfilm.png` as one token.
    """
    return _TOKEN.findall(string.lower())


@dataclass
class ObjectRows:
    """Search index rows of a single object."""

    handle: str
    obj_type: str
    private: bool
    change: float
    # (kind, variant, private, content)
    docs: list[tuple[str, str, bool, str]] = field(default_factory=list)
    # (to_handle, kind, private)
    refs: list[tuple[str, str, bool]] = field(default_factory=list)


def own_strings(obj: GrampsObject) -> tuple[str, str]:
    """Return the object's own text without and with private child objects."""
    strings = obj.get_text_data_list()
    private_strings: list[str] = []
    if hasattr(obj, "gramps_id") and obj.gramps_id not in strings:
        # repositories and notes currently don't have gramps_id on their
        # text_data_list, so it is added here explicitly if missing
        strings.append(obj.gramps_id)
    for child_obj in obj.get_text_data_child_list():
        if not hasattr(child_obj, "get_text_data_list"):
            continue
        target = private_strings if getattr(child_obj, "private", False) else strings
        target += child_obj.get_text_data_list()
        if isinstance(child_obj, Name):
            # for names, need to iterate one level deeper to also find surnames
            for grandchild_obj in child_obj.get_text_data_child_list():
                if hasattr(grandchild_obj, "get_text_data_list"):
                    target += grandchild_obj.get_text_data_list()
    return process_strings(strings), process_strings(strings + private_strings)


def name_string(name: Name) -> str:
    """Return the text of a name, without its type.

    The type ("Birth Name") is left out because families and events are
    found through their people's names: "birth" would match every person.
    """
    strings = [
        name.first_name,
        name.call,
        name.nick,
        name.title,
        name.suffix,
        name.famnick,
    ]
    for surname in name.get_surname_list():
        strings += [surname.prefix, surname.surname, surname.connector]
    return process_strings([string for string in strings if string])


def process_strings(strings: Sequence[str]) -> str:
    """Process a list of strings to a joined string.

    Removes duplicates and adds transliterated strings for strings containing
    unicode characters.
    """

    def generator():
        all_strings = set()
        for string in strings:
            if string not in all_strings:
                all_strings.add(string)
                yield string
                decoded_string = unidecode(string)
                if decoded_string != string and decoded_string not in all_strings:
                    all_strings.add(decoded_string)
                    yield decoded_string

    return " ".join(generator())


def object_rows(obj: GrampsObject, class_name: str) -> ObjectRows:
    """Return the search index rows of a Gramps object."""
    private = bool(getattr(obj, "private", False))
    rows = ObjectRows(
        handle=obj.handle,
        obj_type=class_name.lower(),
        private=private,
        change=obj.change,
    )
    string_public, string_all = own_strings(obj)
    if private:
        rows.docs.append((KIND_OWN, VARIANT_FULL, True, string_all))
    elif string_public == string_all:
        rows.docs.append((KIND_OWN, VARIANT_ALL, False, string_all))
    else:
        rows.docs.append((KIND_OWN, VARIANT_FULL, False, string_all))
        if string_public:
            rows.docs.append((KIND_OWN, VARIANT_REDACTED, False, string_public))
    if isinstance(obj, Person):
        name = obj.get_primary_name()
        string = name_string(name)
        if string:
            rows.docs.append((KIND_NAME, VARIANT_ALL, bool(name.private), string))
        for event_ref in obj.get_event_ref_list():
            if event_ref.get_role().is_primary():
                rows.refs.append(
                    (event_ref.ref, REF_PARTICIPANT, bool(event_ref.private))
                )
    elif isinstance(obj, Family):
        for parent_handle in (obj.father_handle, obj.mother_handle):
            if parent_handle:
                rows.refs.append((parent_handle, REF_PARENT, False))
        for event_ref in obj.get_event_ref_list():
            role = event_ref.get_role()
            if role.is_primary() or role.is_family():
                rows.refs.append(
                    (event_ref.ref, REF_PARTICIPANT, bool(event_ref.private))
                )
    rows.docs = [
        (kind, variant, doc_private, " ".join(tokens))
        for kind, variant, doc_private, content in rows.docs
        if (tokens := tokenize(content))
    ]
    return rows


def object_rows_from_handle(
    db_handle: DbReadBase, class_name: str, handle: str
) -> Optional[ObjectRows]:
    """Return the search index rows of an object, or None if it doesn't exist."""
    query_method = db_handle.method("get_%s_from_handle", class_name)
    assert query_method is not None  # type checker
    try:
        obj = query_method(handle)
    except HandleError:
        return None
    if obj is None:
        return None
    return object_rows(obj, class_name)


def iter_object_rows(db_handle: DbReadBase) -> Generator[ObjectRows, None, None]:
    """Iterate over the search index rows of all objects in the database."""
    for class_name in PRIMARY_GRAMPS_OBJECTS:
        plural_name = GRAMPS_OBJECT_PLURAL[class_name]
        iter_method = db_handle.method("iter_%s", plural_name)
        assert iter_method is not None  # type checker
        for obj in iter_method():
            yield object_rows(obj, class_name)
