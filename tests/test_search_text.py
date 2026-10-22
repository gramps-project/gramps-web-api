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

"""Tests for the text that is indexed for search."""

import gramps.gen.lib as lib
import pytest
from gramps.gen.lib import (
    Attribute,
    AttributeType,
    Event,
    EventRef,
    EventRoleType,
    EventType,
    Family,
    FamilyRelType,
    Media,
    MediaRef,
    Name,
    Person,
    PersonRef,
    RepoRef,
    Source,
    Surname,
)
from gramps.gen.lib.json_utils import object_to_dict

from gramps_webapi.api.search.text import (
    FIELD_SPECS,
    GENERIC_EXCLUDED,
    name_string,
    own_strings,
    tokenize,
)
from gramps_webapi.const import GRAMPS_OBJECT_PLURAL, PRIMARY_GRAMPS_OBJECTS
from tests import ExampleDbInMemory


@pytest.mark.parametrize("class_name", sorted(FIELD_SPECS))
def test_every_field_decided(class_name):
    """Every text or object field of Gramps' schema is indexed or excluded.

    Fails when a new Gramps version adds a field, so that someone decides
    whether it is searchable.
    """
    spec = FIELD_SPECS[class_name]
    decided = [
        *spec.text,
        *spec.types,
        *spec.custom_types,
        *spec.children,
        *spec.excluded,
    ]
    assert len(decided) == len(set(decided)), "a field is listed twice"
    properties = getattr(lib, class_name).get_schema()["properties"]
    assert not set(decided) - set(properties), "unknown field"
    undecided = set()
    for field, prop in properties.items():
        types = prop.get("type")
        types = types if isinstance(types, list) else [types]
        if set(types) <= {"integer", "boolean", "number"}:
            continue
        if field not in decided and field not in GENERIC_EXCLUDED:
            undecided.add(field)
    assert not undecided, f"{class_name}: neither indexed nor excluded"


def _person(**kwargs) -> Person:
    person = Person()
    name = Name()
    name.set_first_name("John")
    surname = Surname()
    surname.set_surname("Smith")
    name.add_surname(surname)
    person.set_primary_name(name)
    for key, value in kwargs.items():
        getattr(person, key)(value)
    return person


def _attribute(value, private=False, type_=AttributeType.AGE) -> Attribute:
    attribute = Attribute()
    attribute.set_type(type_)
    attribute.set_value(value)
    attribute.set_privacy(private)
    return attribute


def _words(text: str) -> set[str]:
    return set(tokenize(text))


def test_labels_not_indexed():
    event_ref = EventRef()
    event_ref.set_role(EventRoleType.PRIMARY)
    public, full = own_strings(_person(add_event_ref=event_ref))
    assert public == full
    assert _words(full) == {"john", "smith"}


def test_reference_text_not_indexed():
    """Text on references is hidden with them if their target is private.

    It would then depend on another object's privacy, so it is never indexed.
    """
    event_ref = EventRef()
    event_ref.add_attribute(_attribute("zqeventref"))
    media_ref = MediaRef()
    media_ref.add_attribute(_attribute("zqmediaref"))
    person_ref = PersonRef()
    person_ref.set_relation("zqpersonref")
    person = _person(add_event_ref=event_ref, add_media_reference=media_ref)
    person.add_person_ref(person_ref)
    repo_ref = RepoRef()
    repo_ref.set_call_number("zqreporef")
    source = Source()
    source.add_repo_reference(repo_ref)
    words = _words(own_strings(person)[1]) | _words(own_strings(source)[1])
    assert not words & {"zqeventref", "zqmediaref", "zqpersonref", "zqreporef"}


def _visit(data, path=""):
    """Yield (path, object) for every object the extraction descends into."""
    yield path, data
    for key in FIELD_SPECS[data["_class"]].children:
        children = data.get(key)
        for child in children if isinstance(children, list) else [children]:
            if isinstance(child, dict):
                yield from _visit(child, f"{path}{data['_class']}.{key}/")


def test_no_reference_descended_into():
    """No indexed text comes from a reference to another object."""
    db = ExampleDbInMemory().load()
    try:
        for class_name in PRIMARY_GRAMPS_OBJECTS:
            for obj in db.method("iter_%s", GRAMPS_OBJECT_PLURAL[class_name])():
                for path, data in _visit(object_to_dict(obj)):
                    assert "ref" not in data, f"descends into a reference: {path}"
    finally:
        db.close()


def test_private_name():
    """Privacy covers everything below a private object."""
    name = Name()
    name.set_first_name("Zqhidden")
    surname = Surname()
    surname.set_surname("Zqsurname")
    name.add_surname(surname)
    name.set_privacy(True)
    attribute = _attribute("zqattribute", private=True)
    person = _person(add_alternate_name=name, add_attribute=attribute)
    public, full = own_strings(person)
    assert not {"zqhidden", "zqsurname", "zqattribute"} & _words(public)
    assert {"zqhidden", "zqsurname", "zqattribute"} <= _words(full)


def test_types():
    event = Event()
    event.set_type(EventType.BIRTH)
    assert _words(own_strings(event)[1]) == {"birth"}
    event.set_type((EventType.CUSTOM, "Zqcustom"))
    assert _words(own_strings(event)[1]) == {"zqcustom"}
    family = Family()
    family.set_relationship(FamilyRelType.UNKNOWN)
    assert own_strings(family)[1] == ""
    family.set_relationship(FamilyRelType.MARRIED)
    assert _words(own_strings(family)[1]) == {"married"}
    # attribute types only if entered by the user
    media = Media()
    media.add_attribute(_attribute("x", type_=AttributeType.AGE))
    media.add_attribute(_attribute("y", type_=(AttributeType.CUSTOM, "Zqtype")))
    assert _words(own_strings(media)[1]) == {"x", "y", "zqtype"}


def test_name_string():
    name = Name()
    name.set_first_name("John")
    name.set_type((lib.NameType.CUSTOM, "Zqtype"))
    surname = Surname()
    surname.set_surname("Smith")
    surname.set_prefix("von")
    name.add_surname(surname)
    assert _words(name_string(name)) == {"john", "von", "smith"}
