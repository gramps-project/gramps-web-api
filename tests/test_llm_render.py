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

"""Tests for rendering Gramps objects for the AI assistant."""

import unittest

from gramps.gen.db import DbTxn
from gramps.gen.lib import Attribute, AttributeType, Event, EventRef, EventType

from gramps_webapi.api.llm.render import render_object
from gramps_webapi.api.util import ModifiedPrivateProxyDb

from . import ExampleDbInMemory


def _render(db, class_name, gramps_id):
    obj = db.method("get_%s_from_gramps_id", class_name)(gramps_id)
    return render_object(db, class_name, obj)


class TestRender(unittest.TestCase):
    """Rendering of the example tree."""

    @classmethod
    def setUpClass(cls):
        cls.exampledb = ExampleDbInMemory()
        cls.db = cls.exampledb.load()
        cls.proxy = ModifiedPrivateProxyDb(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.exampledb.close()

    def test_person(self):
        text = _render(self.db, "Person", "I0044")
        self.assertTrue(
            text.startswith("## Person: [Lewis Anderson Garner von Zieliński Sr]")
        )
        self.assertIn("Gender: male", text)
        self.assertIn(
            "- [Birth](/event/E1656): 1855-06-21 in [Great Falls](/place/P1435)", text
        )
        # parents, spouse, and children
        self.assertIn("Parents ([family](/family/F0018)): [Robert W. Garner]", text)
        self.assertIn("with [Luella Jacques Martel](/person/I0045)", text)
        self.assertIn("[Eugene Stanley Garner](/person/I0046)", text)

    def test_person_name_details(self):
        text = _render(self.db, "Person", "I0044")
        self.assertIn(
            "Name details: title Dr., call name Anderson, nickname Big Louie, "
            "family nickname Beauregard",
            text,
        )

    def test_person_attribute_fields(self):
        text = _render(self.db, "Person", "I0044")
        self.assertIn("Description: 10 fingers, 10 toes.", text)
        self.assertIn("1600 Pennsylvania Ave.", text)
        self.assertIn("http://www.gramps-project.org/", text)

    def test_person_notes_are_previews(self):
        text = _render(self.db, "Person", "I0044")
        self.assertIn("- [N0003](/note/N0003) (Person Note): We have committed", text)
        self.assertNotIn("Mission Statement Generator", text)

    def test_note(self):
        text = _render(self.db, "Note", "N0003")
        self.assertIn("Referenced by: [Lewis Anderson Garner", text)
        self.assertIn("Mission Statement Generator", text)

    def test_event_participants(self):
        text = _render(self.db, "Event", "E1656")
        self.assertIn("Participants:\n- [Lewis Anderson Garner", text)

    def test_private_attribute(self):
        person = self.db.get_person_from_gramps_id("I0044")
        full = render_object(self.db, "Person", person)
        public = render_object(
            self.proxy, "Person", self.proxy.get_person_from_handle(person.handle)
        )
        self.assertIn("123-456-7890", full)
        self.assertNotIn("123-456-7890", public)
        self.assertIn("10 fingers, 10 toes.", public)


class TestRenderModified(unittest.TestCase):
    """Rendering after changing the example tree; each test gets a fresh copy."""

    def setUp(self):
        self.exampledb = ExampleDbInMemory()
        self.db = self.exampledb.load()
        self.proxy = ModifiedPrivateProxyDb(self.db)
        self.person = self.db.get_person_from_gramps_id("I0044")

    def tearDown(self):
        self.db.close()
        self.exampledb.close()

    def _public(self, class_name, gramps_id):
        obj = self.db.method("get_%s_from_gramps_id", class_name)(gramps_id)
        return render_object(
            self.proxy,
            class_name,
            self.proxy.method("get_%s_from_handle", class_name)(obj.handle),
        )

    def test_skipped_gedcom_types(self):
        with DbTxn("add GEDCOM data", self.db) as trans:
            for type_name, value in [("_UID", "ABC123"), ("RIN", "4711")]:
                attribute = Attribute()
                attribute.set_type((AttributeType.CUSTOM, type_name))
                attribute.set_value(value)
                self.person.add_attribute(attribute)
            event = Event()
            event.set_type((EventType.CUSTOM, "_UPD"))
            self.db.add_event(event, trans)
            event_ref = EventRef()
            event_ref.ref = event.handle
            self.person.add_event_ref(event_ref)
            self.db.commit_person(self.person, trans)
        text = _render(self.db, "Person", "I0044")
        self.assertNotIn("ABC123", text)
        self.assertNotIn("4711", text)
        self.assertNotIn("_UPD", text)
        self.assertIn("Nickname: Big Louie", text)

    def test_private_media_reference_not_a_backlink(self):
        self.assertIn("/person/I0044", self._public("Media", "O0008"))
        with DbTxn("make media reference private", self.db) as trans:
            for media_ref in self.person.get_media_list():
                media_ref.set_privacy(True)
            self.db.commit_person(self.person, trans)
        self.assertIn("/person/I0044", _render(self.db, "Media", "O0008"))
        self.assertNotIn("/person/I0044", self._public("Media", "O0008"))

    def test_private_event_reference_not_a_participant(self):
        self.assertIn("/person/I0044", self._public("Event", "E1656"))
        with DbTxn("make event reference private", self.db) as trans:
            for event_ref in self.person.get_event_ref_list():
                event_ref.set_privacy(True)
            self.db.commit_person(self.person, trans)
        self.assertIn("/person/I0044", _render(self.db, "Event", "E1656"))
        self.assertNotIn("/person/I0044", self._public("Event", "E1656"))

    def test_private_spouse(self):
        spouse = self.db.get_person_from_gramps_id("I0045")
        with DbTxn("make spouse private", self.db) as trans:
            spouse.set_privacy(True)
            self.db.commit_person(spouse, trans)
        self.assertIn("/person/I0045", _render(self.db, "Person", "I0044"))
        self.assertNotIn("/person/I0045", self._public("Person", "I0044"))

    def test_private_child_reference(self):
        parents = "Parents ([family](/family/F0018))"
        self.assertIn(parents, self._public("Person", "I0044"))
        family = self.db.get_family_from_gramps_id("F0018")
        with DbTxn("make child reference private", self.db) as trans:
            for child_ref in family.get_child_ref_list():
                if child_ref.ref == self.person.handle:
                    child_ref.set_privacy(True)
            self.db.commit_family(family, trans)
        self.assertIn(parents, _render(self.db, "Person", "I0044"))
        self.assertNotIn(parents, self._public("Person", "I0044"))

    def test_parent_family_without_child_reference(self):
        family = self.db.get_family_from_gramps_id("F0018")
        with DbTxn("remove child reference", self.db) as trans:
            family.set_child_ref_list(
                [
                    child_ref
                    for child_ref in family.get_child_ref_list()
                    if child_ref.ref != self.person.handle
                ]
            )
            self.db.commit_family(family, trans)
        self.assertNotIn("Parents (", _render(self.db, "Person", "I0044"))

    def test_family_without_person_as_parent(self):
        # I0044's own parents' family, wrongly listed as one of his families
        family = self.db.get_family_from_gramps_id("F0018")
        with DbTxn("add inconsistent family", self.db) as trans:
            self.person.add_family_handle(family.handle)
            self.db.commit_person(self.person, trans)
        text = _render(self.db, "Person", "I0044")
        self.assertNotIn("- [family](/family/F0018)", text)
        self.assertIn("- [family](/family/F0017)", text)

    def test_place_name_with_comma(self):
        place = self.db.get_place_from_gramps_id("P1435")
        with DbTxn("rename place", self.db) as trans:
            name = place.get_name()
            name.set_value("Great Falls, Cascade County")
            place.set_name(name)
            self.db.commit_place(place, trans)
        text = _render(self.db, "Place", "P1435")
        self.assertIn("## Place: [Great Falls, Cascade County](/place/P1435)", text)
        self.assertIn("Part of: MT, USA", text)
