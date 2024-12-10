#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2024      David Straub
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

"""Functions for converting Gramps objects to indexable text."""

from typing import Any, Dict, Generator, Optional, Sequence, Tuple

from gramps.gen.db.base import DbReadBase
from gramps.gen.lib import (
    Event,
    Family,
    Name,
    Person,
    Place,
    Citation,
    Source,
    Repository,
    Note,
    Media,
)
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from unidecode import unidecode

from ...const import GRAMPS_OBJECT_PLURAL, PRIMARY_GRAMPS_OBJECTS
from ..resources.util import get_event_participants_for_handle
from .text_semantic import (
    person_to_text,
    family_to_text,
    event_to_text,
    place_to_text,
    citation_to_text,
    source_to_text,
    repository_to_text,
    note_to_text,
    media_to_text,
)


def object_to_strings(obj: GrampsObject, db_handle: DbReadBase) -> Tuple[str, str]:
    """Create strings from a Gramps object's textual pieces.

    This function returns a tuple of two strings: the first one contains
    the concatenated string of the object and the strings of all
    non-private child objects. The second contains the concatenated
    strings of the objects and all non-private *and* private child objects."""
    strings = obj.get_text_data_list()
    private_strings = []
    if hasattr(obj, "gramps_id") and obj.gramps_id not in strings:
        # repositories and notes currently don't have gramps_id on their
        # text_data_list, so it is added here explicitly if missing
        strings.append(obj.gramps_id)
    text_data_child_list = obj.get_text_data_child_list()
    # family: add parents' names
    if isinstance(obj, Family):
        for parent_handle in [obj.father_handle, obj.mother_handle]:
            if parent_handle:
                parent_obj = db_handle.get_person_from_handle(parent_handle)
                text_data_child_list.append(parent_obj.get_primary_name())
    # event: add primary/family role participants' names
    if isinstance(obj, Event):
        participants = get_event_participants_for_handle(db_handle, obj.handle)
        for role, person in participants["people"]:
            if role.is_primary():
                text_data_child_list.append(person.get_primary_name())
        for role, family in participants["families"]:
            if role.is_primary() or role.is_family():
                for parent_handle in [family.father_handle, family.mother_handle]:
                    if parent_handle:
                        parent_obj = db_handle.get_person_from_handle(parent_handle)
                        text_data_child_list.append(parent_obj.get_primary_name())
    for child_obj in text_data_child_list:
        if hasattr(child_obj, "get_text_data_list"):
            if hasattr(child_obj, "private") and child_obj.private:
                private_strings += child_obj.get_text_data_list()
            else:
                strings += child_obj.get_text_data_list()
            if isinstance(child_obj, Name):
                # for names, need to iterate one level deeper to also find surnames
                for grandchild_obj in child_obj.get_text_data_child_list():
                    if hasattr(grandchild_obj, "get_text_data_list"):
                        if hasattr(child_obj, "private") and child_obj.private:
                            private_strings += grandchild_obj.get_text_data_list()
                        else:
                            strings += grandchild_obj.get_text_data_list()
    return process_strings(strings), process_strings(strings + private_strings)


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


def object_to_strings_semantic(
    obj: GrampsObject, db_handle: DbReadBase
) -> Tuple[str, str]:
    """Create strings from a Gramps object's textual pieces.

    This function returns a tuple of two strings: the first one contains
    the concatenated string of the object and the strings of all
    non-private child objects. The second contains the concatenated
    strings of all private child objects."""
    if isinstance(obj, Person):
        return person_to_text(obj, db_handle)
    if isinstance(obj, Family):
        return family_to_text(obj, db_handle)
    if isinstance(obj, Event):
        return event_to_text(obj, db_handle)
    if isinstance(obj, Place):
        return place_to_text(obj, db_handle)
    if isinstance(obj, Citation):
        return citation_to_text(obj, db_handle)
    if isinstance(obj, Source):
        return source_to_text(obj, db_handle)
    if isinstance(obj, Repository):
        return repository_to_text(obj, db_handle)
    if isinstance(obj, Media):
        return media_to_text(obj, db_handle)
    if isinstance(obj, Note):
        return note_to_text(obj, db_handle)
    else:
        return "", ""


def obj_strings_from_handle(
    db_handle: DbReadBase, class_name: str, handle, semantic: bool = False
) -> Optional[Dict[str, Any]]:
    """Return object strings from a handle and Gramps class name."""
    query_method = db_handle.method("get_%s_from_handle", class_name)
    assert query_method is not None  # type checker
    obj = query_method(handle)
    return obj_strings_from_object(
        db_handle=db_handle, class_name=class_name, obj=obj, semantic=semantic
    )


def obj_strings_from_object(
    db_handle: DbReadBase, class_name: str, obj: GrampsObject, semantic: bool = False
) -> Optional[Dict[str, Any]]:
    """Return object strings from a handle and Gramps class name."""
    if semantic:
        obj_string_public, obj_string_all = object_to_strings_semantic(obj, db_handle)
    else:
        obj_string_public, obj_string_all = object_to_strings(obj, db_handle)
    private = hasattr(obj, "private") and obj.private
    if obj_string_all:
        return {
            "class_name": class_name,
            "handle": obj.handle,
            "private": private,
            "string_public": obj_string_public,
            "string_all": obj_string_all,
            "change": obj.change,
        }
    return None


def iter_obj_strings(
    db_handle: DbReadBase, semantic: bool = False
) -> Generator[Dict[str, Any], None, None]:
    """Iterate over object strings in the whole database."""
    for class_name in PRIMARY_GRAMPS_OBJECTS:
        plural_name = GRAMPS_OBJECT_PLURAL[class_name]
        iter_method = db_handle.method("iter_%s", plural_name)
        assert iter_method is not None  # type checker
        for obj in iter_method():
            obj_strings = obj_strings_from_object(
                db_handle, class_name, obj, semantic=semantic
            )
            if obj_strings:
                yield obj_strings
