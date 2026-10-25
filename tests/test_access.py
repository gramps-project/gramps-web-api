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

"""Tests for RestrictedDb and the sanitizer."""

import pytest
from gramps.gen.db import DbTxn
from gramps.gen.db.dbconst import CLASS_TO_KEY_MAP
from gramps.gen.db.utils import open_database
from gramps.gen.lib import (
    Citation,
    Date,
    Event,
    EventRef,
    EventType,
    Note,
    Source,
    StyledText,
    StyledTextTag,
    StyledTextTagType,
)
from gramps.gen.lib.json_utils import data_to_object, object_to_data, remove_object
from gramps.gen.proxy import PrivateProxyDb
from gramps.gen.proxy.proxybase import ProxyDbBase

from gramps_webapi.api.access import AccessPolicy, RestrictedDb
from gramps_webapi.api.access.db import CLASS_NAMES, ITER_NAMES, TABLES
from gramps_webapi.api.access.sanitize import sanitize
from gramps_webapi.api.resources.filters import _ADDITIONAL_RULES, MatchesQuery
from tests import ExampleDbSQLite
from tests.test_privacy_canary import _person, _plant

TREE_NAME = "access"
GUEST = AccessPolicy(view_private=False)


def _data(obj):
    return remove_object(object_to_data(obj))


def _normalized(data):
    """Raw data as Gramps' private proxy builds it, for comparisons."""
    if data.get("_class") == "Media" and data.get("path") == "":
        # the proxy's set_path() normalizes "" to "."
        data = {**data, "path": "."}
    return data


@pytest.fixture(scope="module")
def tree():
    """The example tree with the privacy canaries and some more cases."""
    ExampleDbSQLite(name=TREE_NAME)
    db = open_database(TREE_NAME, force_unlock=True)
    _plant(db)
    handles = {}
    with DbTxn("add cases", db) as trans:
        # a citation of a private source, and one without a source
        source = Source()
        source.set_title("private source")
        source.set_privacy(True)
        db.add_source(source, trans)
        citation = Citation()
        citation.set_reference_handle(source.handle)
        db.add_citation(citation, trans)
        handles["citation_private_source"] = citation.handle
        citation = Citation()
        db.add_citation(citation, trans)
        handles["citation_no_source"] = citation.handle
        # a note linking to a private person, and one to a public person
        private_person = _person(db, trans, "Hidden", private=True)
        public_person = _person(db, trans, "Shown")
        for key, target in (
            ("note_private_link", private_person),
            ("note_public_link", public_person),
        ):
            link = f"gramps://Person/handle/{target.handle}"
            note = Note()
            note.set_styledtext(
                StyledText(
                    "see", [StyledTextTag(StyledTextTagType.LINK, link, [(0, 3)])]
                )
            )
            db.add_note(note, trans)
            handles[key] = note.handle
        # a person whose first event reference is private, so the birth index
        # must move
        person = _person(db, trans, "Indexed")
        for event_type, private_ref in (
            (EventType.RESIDENCE, True),
            (EventType.BIRTH, False),
        ):
            event = Event()
            event.set_type(event_type)
            date = Date()
            date.set_yr_mon_day(1900, 1, 1)
            event.set_date_object(date)
            db.add_event(event, trans)
            ref = EventRef()
            ref.set_reference_handle(event.handle)
            ref.set_privacy(private_ref)
            person.add_event_ref(ref)
        person.set_birth_ref(ref)
        db.commit_person(person, trans)
        handles["person_birth_index"] = person.handle
    yield db, handles
    db.close()


def test_no_way_to_the_base_db(tree):
    db, _ = tree
    restricted = RestrictedDb(db, GUEST)
    assert not isinstance(restricted, ProxyDbBase)
    for name in ("db", "dbapi", "serializer", "undodb", "dbstate"):
        assert not hasattr(restricted, name)
    assert restricted.basedb is restricted
    # the only reference to the base database is the name-mangled one
    referring = [name for name, value in vars(restricted).items() if value is db]
    assert referring == ["_RestrictedDb__db"]


def test_unimplemented_methods_fail(tree):
    db, _ = tree
    restricted = RestrictedDb(db, GUEST)
    with pytest.raises(NotImplementedError):
        restricted.has_person_gramps_id("I0001")


def test_same_as_private_proxy(tree):
    """Without grants, RestrictedDb shows what Gramps' private proxy shows,
    except for deliberate differences, which the extra cases cover."""
    db, handles = tree
    proxy = PrivateProxyDb(db)
    restricted = RestrictedDb(db, GUEST)
    deliberate = {handles["citation_private_source"], handles["note_private_link"]}
    for class_name in CLASS_NAMES:
        table = TABLES[class_name]
        expected = set(proxy.method("iter_%s_handles", table)()) - deliberate
        assert set(restricted.method("iter_%s_handles", table)()) == expected
        count = restricted.method("get_number_of_%s", ITER_NAMES[class_name])()
        assert count == len(expected)
        for handle in expected:
            obj = proxy.method("get_%s_from_handle", table)(handle)
            # a new database for each object, to also cover single lookups
            single = RestrictedDb(db, GUEST)
            for database in (restricted, single):
                data = _data(database.method("get_%s_from_handle", table)(handle))
                assert _normalized(data) == _data(obj), (class_name, handle)
            by_id = restricted.method("get_%s_from_gramps_id", table)(obj.gramps_id)
            assert _data(by_id) == _data(
                restricted.method("get_%s_from_handle", table)(handle)
            )


def test_hidden_objects(tree):
    db, handles = tree
    restricted = RestrictedDb(db, GUEST)
    assert (
        restricted.get_citation_from_handle(handles["citation_private_source"]) is None
    )
    assert (
        restricted.get_citation_from_handle(handles["citation_no_source"]) is not None
    )
    assert restricted.get_note_from_handle(handles["note_private_link"]) is None
    assert restricted.get_note_from_handle(handles["note_public_link"]) is not None


def test_birth_index_follows_removed_references(tree):
    db, handles = tree
    person = RestrictedDb(db, GUEST).get_person_from_handle(
        handles["person_birth_index"]
    )
    assert len(person.get_event_ref_list()) == 1
    assert person.birth_ref_index == 0
    event = db.get_event_from_handle(person.get_birth_ref().ref)
    assert event.get_type() == EventType.BIRTH


def test_sanitizer_knows_all_references(tree):
    """With nothing visible, no references may be left, except to tags and
    note links, which are handled by the visibility of notes."""
    db, _ = tree
    for class_name in CLASS_NAMES:
        for _, data in db._iter_raw_data(CLASS_TO_KEY_MAP[class_name]):
            clean = sanitize(data, lambda target, handle: target == "Tag")
            obj = data_to_object(clean)
            left = {
                (target, handle)
                for target, handle in obj.get_referenced_handles_recursively()
                if target != "Tag"
            }
            if class_name == "Note":
                left -= {(t, h) for t, h in obj.get_referenced_handles()}
            assert not left, (class_name, data["handle"], left)


def test_owner_sees_everything(tree):
    db, _ = tree
    restricted = RestrictedDb(db, AccessPolicy(view_private=True))
    for class_name in CLASS_NAMES:
        table = TABLES[class_name]
        assert set(restricted.method("iter_%s_handles", table)()) == set(
            db.method("iter_%s_handles", table)()
        )


def test_goql_rule_does_not_use_sql(tree):
    """The GOQL filter rule must evaluate each object of a restricted db."""
    db, _ = tree
    restricted = RestrictedDb(db, GUEST)
    rule_class = next(
        rule for rule in _ADDITIONAL_RULES["Person"] if issubclass(rule, MatchesQuery)
    )
    rule = rule_class(["gender == 1"])
    rule.prepare(restricted, None)
    assert rule.selected_handles is None
    rule.prepare(db, None)
    assert rule.selected_handles is not None
