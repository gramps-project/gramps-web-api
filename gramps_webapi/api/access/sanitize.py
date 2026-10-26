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

"""Remove what a user may not see from the raw data of an object.

Works on raw data (the dicts Gramps stores as JSON), not on objects, since
Gramps filters read raw data through cursors. Objects are built from the
sanitized raw data.
"""

from __future__ import annotations

from typing import Callable, Iterator, Optional, Union

from gramps.gen import lib
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.lib import Name, Surname
from gramps.gen.lib.json_utils import object_to_data, remove_object

_ = glocale.translation.gettext

# a value in the raw data of an object, as stored as JSON
JsonValue = Union[
    None, bool, int, float, str, list["JsonValue"], dict[str, "JsonValue"]
]
JsonObject = dict[str, JsonValue]
# the raw data of an object
RawData = JsonObject
# (class name, handle) -> visible
IsVisible = Callable[[str, Optional[str]], bool]

# lists of handles, in any object
HANDLE_LISTS: dict[str, str] = {
    "citation_list": "Citation",
    "note_list": "Note",
    "family_list": "Family",
    "parent_family_list": "Family",
}
# objects in lists, by their class, whose `ref` is a handle
REFERENCE_CLASSES: dict[str, str] = {
    "EventRef": "Event",
    "ChildRef": "Person",
    "PersonRef": "Person",
    "MediaRef": "Media",
    "RepoRef": "Repository",
    "PlaceRef": "Place",
}
# single handles: (class name, key) -> (referenced class name, empty value)
HANDLE_FIELDS: dict[tuple[str, str], tuple[str, Optional[str]]] = {
    ("Family", "father_handle"): ("Person", None),
    ("Family", "mother_handle"): ("Person", None),
    ("Event", "place"): ("Place", ""),
    ("LdsOrd", "place"): ("Place", ""),
    ("LdsOrd", "famc"): ("Family", None),
    ("Citation", "source_handle"): ("Source", None),
}

LINK_PREFIX = "gramps://"


def as_object(value: JsonValue) -> JsonObject:
    """Return a JSON value that must be an object."""
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object, got {type(value).__name__}")
    return value


def as_list(value: JsonValue) -> list[JsonValue]:
    """Return a JSON value that must be a list."""
    if not isinstance(value, list):
        raise TypeError(f"Expected a JSON list, got {type(value).__name__}")
    return value


def as_handle(value: JsonValue) -> Optional[str]:
    """Return a JSON value that must be a handle, or empty."""
    if value is not None and not isinstance(value, str):
        raise TypeError(f"Expected a handle, got {type(value).__name__}")
    return value


def _class_name(value: JsonObject) -> Optional[str]:
    class_name = value.get("_class")
    return class_name if isinstance(class_name, str) else None


def private_name() -> RawData:
    """Raw data of the name shown for a person whose name is private."""
    name = Name()
    surname = Surname()
    surname.set_surname(_("Private"))
    name.set_surname_list([surname])
    name.set_primary_surname()
    return as_object(remove_object(object_to_data(name)))


def _schema_class_name(properties: JsonObject) -> Optional[str]:
    """Return the class name a JSON schema's properties describe."""
    class_schema = properties.get("_class")
    if not isinstance(class_schema, dict):
        return None
    enum = class_schema.get("enum")
    if isinstance(enum, list) and enum and isinstance(enum[0], str):
        return enum[0]
    return None


def _schema_keys(schema: JsonObject, keys: dict[Optional[str], set[str]]) -> bool:
    """Collect, by class name, the keys under which there can be something to
    remove. Return whether there can be something in `schema` at all."""
    if schema.get("type") == "array":
        items = as_object(schema.get("items", {}))
        found = _schema_keys(items, keys)
        properties = as_object(items.get("properties", {}))
        class_name = _schema_class_name(properties)
        return found or "private" in properties or class_name in REFERENCE_CLASSES
    properties_value = schema.get("properties")
    if not properties_value:
        return False
    properties = as_object(properties_value)
    class_name = _schema_class_name(properties)
    relevant = keys.setdefault(class_name, set())
    for key, subschema in properties.items():
        if (
            key in HANDLE_LISTS
            or (class_name, key) in HANDLE_FIELDS
            or _schema_keys(as_object(subschema), keys)
        ):
            relevant.add(key)
    return bool(relevant)


def _relevant_keys() -> dict[str, frozenset[str]]:
    keys: dict[Optional[str], set[str]] = {}
    for class_name in (
        "Person",
        "Family",
        "Event",
        "Place",
        "Source",
        "Citation",
        "Media",
        "Repository",
        "Note",
    ):
        _schema_keys(getattr(lib, class_name).get_schema(), keys)
    return {
        class_name: frozenset(value)
        for class_name, value in keys.items()
        if class_name is not None
    }


# class name -> keys under which there can be something to remove
RELEVANT_KEYS = _relevant_keys()


def sanitize(data: RawData, is_visible: IsVisible) -> RawData:
    """Return a copy of a visible object's raw data without hidden parts.

    Removes private secondary objects, references to objects that aren't
    visible, and Gramps' cached `_object`, which would otherwise be returned
    instead of the sanitized data.

    `data` must be raw data as read from the database: parts that can't
    contain anything to remove are shared with the result, not copied.
    """
    clean = _clean_object(data, is_visible)
    if _class_name(data) == "Person":
        _sanitize_person(data, clean, is_visible)
    return clean


def _clean(value: JsonValue, is_visible: IsVisible) -> JsonValue:
    if isinstance(value, dict):
        return _clean_object(value, is_visible)
    if isinstance(value, list):
        return _clean_list(value, is_visible)
    return value


def _clean_object(value: JsonObject, is_visible: IsVisible) -> JsonObject:
    class_name = _class_name(value)
    relevant = RELEVANT_KEYS.get(class_name) if class_name else None
    if relevant is None:
        # unknown class: check everything
        relevant = frozenset(value)
    result = dict(value)
    result.pop("_object", None)
    for key in relevant:
        if key not in value:
            continue
        item = value[key]
        field = HANDLE_FIELDS.get((class_name, key)) if class_name else None
        if field is not None:
            target, empty = field
            handle = as_handle(item)
            result[key] = empty if handle and not is_visible(target, handle) else item
            continue
        target_class = HANDLE_LISTS.get(key)
        if target_class is not None and isinstance(item, list):
            result[key] = [h for h in item if is_visible(target_class, as_handle(h))]
            continue
        result[key] = _clean(item, is_visible)
    return result


def _clean_list(value: list[JsonValue], is_visible: IsVisible) -> list[JsonValue]:
    result: list[JsonValue] = []
    for item in value:
        if isinstance(item, dict):
            # private secondary objects
            if item.get("private"):
                continue
            target = REFERENCE_CLASSES.get(_class_name(item) or "")
            if target is not None and not is_visible(
                target, as_handle(item.get("ref"))
            ):
                continue
        result.append(_clean(item, is_visible))
    return result


def _sanitize_person(data: RawData, clean: RawData, is_visible: IsVisible) -> None:
    if as_object(data["primary_name"]).get("private"):
        clean["primary_name"] = private_name()
    # birth and death are indexes into the event references, some of which
    # may have been removed
    kept = [
        not ref.get("private") and is_visible("Event", as_handle(ref.get("ref")))
        for ref in map(as_object, as_list(data["event_ref_list"]))
    ]
    for key in ("birth_ref_index", "death_ref_index"):
        index = data.get(key, -1)
        if isinstance(index, int) and 0 <= index < len(kept) and kept[index]:
            clean[key] = sum(kept[:index])
        else:
            clean[key] = -1


def note_links(data: RawData) -> Iterator[tuple[str, str, str]]:
    """Yield (class name, "handle" or "gramps_id", value) of a note's links."""
    text = as_object(data.get("text") or {})
    for tag in map(as_object, as_list(text.get("tags", []))):
        value = tag.get("value")
        if not isinstance(value, str) or not value.startswith(LINK_PREFIX):
            continue
        parts = value[len(LINK_PREFIX) :].split("/")
        if len(parts) == 3 and parts[1] in ("handle", "gramps_id"):
            yield parts[0], parts[1], parts[2]
