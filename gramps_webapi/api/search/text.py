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
from typing import Any, Generator, Optional, Sequence

import gramps.gen.lib
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib import Family, Name, Person
from gramps.gen.lib.json_utils import object_to_dict
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


@dataclass(frozen=True)
class FieldSpec:
    """What of an object of a given class is indexed.

    Fields are named as in the object's JSON representation. Every text,
    object and object list field of the class must be in exactly one of the
    tuples, or in GENERIC_EXCLUDED; a test checks this against Gramps' schema,
    so that a field added by a new Gramps version needs a decision.
    """

    text: tuple[str, ...] = ()
    # type fields: a standard type untranslated (e.g. "Birth"), as the
    # server's language is not the user's; a custom type as entered
    types: tuple[str, ...] = ()
    # type fields indexed only if custom, i.e. entered by the user
    custom_types: tuple[str, ...] = ()
    # child objects or lists of them, indexed with their own FieldSpec
    children: tuple[str, ...] = ()
    # deliberately not indexed
    excluded: tuple[str, ...] = ()


# not text: identifiers, references to other objects, privacy and dates
# (dates are better searched with filters)
GENERIC_EXCLUDED = {
    "_class",
    "handle",
    "change",
    "private",
    "ref",
    "citation_list",
    "note_list",
    "tag_list",
    "date",
}

_ADDRESS = ("street", "locality", "city", "county", "state", "country", "postal")
_ATTRIBUTE = FieldSpec(text=("value",), custom_types=("type",))

# References to other objects (event, media, person and repository references,
# and their attributes) are never indexed, not even their text: Gramps hides a
# reference completely if its target is private, so its text would depend on
# another object's privacy. An object's indexed text depends only on the object.
FIELD_SPECS: dict[str, FieldSpec] = {
    # primary objects
    "Person": FieldSpec(
        text=("gramps_id",),
        children=(
            "primary_name",
            "alternate_names",
            "attribute_list",
            "address_list",
            "urls",
        ),
        excluded=(
            "family_list",
            "parent_family_list",
            "event_ref_list",
            "person_ref_list",
            "media_list",
            # LDS ordinances, whose only text is a temple code
            "lds_ord_list",
        ),
    ),
    "Family": FieldSpec(
        text=("gramps_id",),
        types=("type",),
        children=("attribute_list",),
        excluded=(
            "father_handle",
            "mother_handle",
            "child_ref_list",
            "event_ref_list",
            "media_list",
            "lds_ord_list",
        ),
    ),
    "Event": FieldSpec(
        text=("gramps_id", "description"),
        types=("type",),
        children=("attribute_list",),
        excluded=("place", "media_list"),
    ),
    "Place": FieldSpec(
        text=("gramps_id", "title", "code"),
        types=("place_type",),
        children=("name", "alt_names", "alt_loc", "urls"),
        excluded=("long", "lat", "placeref_list", "media_list"),
    ),
    "Source": FieldSpec(
        text=("gramps_id", "title", "author", "pubinfo", "abbrev"),
        children=("attribute_list",),
        excluded=("reporef_list", "media_list"),
    ),
    "Citation": FieldSpec(
        text=("gramps_id", "page"),
        children=("attribute_list",),
        excluded=("source_handle", "media_list"),
    ),
    "Repository": FieldSpec(
        text=("gramps_id", "name"),
        types=("type",),
        children=("address_list", "urls"),
    ),
    "Media": FieldSpec(
        text=("gramps_id", "desc", "path"),
        children=("attribute_list",),
        excluded=("mime", "checksum"),
    ),
    "Note": FieldSpec(
        text=("gramps_id",),
        children=("text",),
        excluded=("type",),
    ),
    "Tag": FieldSpec(text=("name",), excluded=("color",)),
    # secondary objects, which are part of the object holding them
    "Name": FieldSpec(
        text=("first_name", "call", "nick", "title", "suffix", "famnick"),
        children=("surname_list",),
        # the type ("Birth Name") would match every person
        excluded=("type", "group_as"),
    ),
    "Surname": FieldSpec(
        text=("prefix", "surname", "connector"),
        excluded=("origintype",),
    ),
    "Attribute": _ATTRIBUTE,
    "SrcAttribute": _ATTRIBUTE,
    "Address": FieldSpec(text=_ADDRESS + ("phone",)),
    "Location": FieldSpec(text=_ADDRESS + ("phone", "parish")),
    "Url": FieldSpec(text=("path", "desc"), excluded=("type",)),
    "PlaceName": FieldSpec(text=("value",), excluded=("lang",)),
    "StyledText": FieldSpec(text=("string",), excluded=("tags",)),
}


def _type_string(data: Any, custom_only: bool) -> str:
    """Return the text of a Gramps type in its JSON representation."""
    if not isinstance(data, dict):
        return ""
    type_class = getattr(gramps.gen.lib, data["_class"])
    gramps_type = type_class((data["value"], data["string"]))
    if gramps_type.is_custom():
        return gramps_type.string
    if custom_only or data["value"] == getattr(type_class, "UNKNOWN", None):
        return ""
    return gramps_type.xml_str()


def _collect(
    data: dict, public: list[str], private: list[str], is_private: bool = False
) -> None:
    """Add the text of an object in its JSON representation, recursively.

    Text of a private object, and of everything below it, goes to `private`.
    """
    spec = FIELD_SPECS[data["_class"]]
    is_private = is_private or bool(data.get("private"))
    strings = private if is_private else public
    strings += [data[key] for key in spec.text if data.get(key)]
    strings += [_type_string(data.get(key), False) for key in spec.types]
    strings += [_type_string(data.get(key), True) for key in spec.custom_types]
    for key in spec.children:
        children = data.get(key)
        for child in children if isinstance(children, list) else [children]:
            if isinstance(child, dict):
                _collect(child, public, private, is_private)


def own_strings(obj: GrampsObject) -> tuple[str, str]:
    """Return the object's own text without and with private child objects."""
    public: list[str] = []
    private: list[str] = []
    data = object_to_dict(obj)
    # the object's own privacy is handled by the caller
    data["private"] = False
    _collect(data, public, private)
    public = [string for string in public if string]
    return process_strings(public), process_strings(
        public + [string for string in private if string]
    )


def name_string(name: Name) -> str:
    """Return the text of a name, without its type.

    The type ("Birth Name") is left out because families and events are
    found through their people's names: "birth" would match every person.
    """
    strings: list[str] = []
    data = object_to_dict(name)
    # the name's privacy is stored with the document
    data["private"] = False
    _collect(data, strings, strings)
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
