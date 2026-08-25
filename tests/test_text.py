#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2024   David Straub
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

"""Test search text functions."""

from gramps.gen.errors import HandleError
from gramps.gen.lib import Event, EventRef, Family

from gramps_webapi.api.search.text_semantic import (
    PString,
    event_to_text,
    family_to_text,
    get_family_title,
)

# tests for the PString class


def test_pstring_add():
    c = PString("a") + PString("b")
    assert c.string_all == "ab"
    assert c.string_public == "ab"


def test_pstring_add_string():
    c = PString("a") + "b"
    assert c.string_all == "ab"
    assert c.string_public == "ab"


def test_pstring_radd_string():
    c = "a" + PString("b")
    assert c.string_all == "ab"
    assert c.string_public == "ab"


def test_pstring_add_public_only():
    c = PString("a", public_only=True) + PString("b", public_only=True)
    assert c.string_all == ""
    assert c.string_public == "ab"


def test_pstring_add_private():
    c = PString("a", private=True) + PString("b", private=True)
    assert c.string_all == "ab"
    assert c.string_public == ""


def test_pstring_iadd():
    c = PString("a")
    c += PString("b")
    assert c.string_all == "ab"
    assert c.string_public == "ab"


def test_pstring_iadd_string():
    c = PString("a")
    c += "b"
    assert c.string_all == "ab"
    assert c.string_public == "ab"


# tests for graceful handling of dangling handles


class DanglingDb:
    """Stub database where every handle lookup fails."""

    def _raise(self, handle):
        raise HandleError(f"Handle {handle} not found")

    get_person_from_handle = _raise
    get_event_from_handle = _raise
    get_place_from_handle = _raise

    def find_backlink_handles(self, handle, include_classes=None):
        return []


def test_event_to_text_dangling_place():
    event = Event()
    event.set_gramps_id("E0000")
    event.set_handle("event-handle")
    event.set_place_handle("does-not-exist")
    public, private = event_to_text(event, DanglingDb())
    assert "E0000" in private
    assert "The event location was" not in private
    assert "The event location was" not in public


def test_get_family_title_dangling_parents():
    family = Family()
    family.set_father_handle("does-not-exist")
    family.set_mother_handle("does-not-exist")
    title = get_family_title(family, DanglingDb())
    assert title.string_all == "Unknown father and unknown mother"
    assert title.string_public == "Unknown father and unknown mother"


def test_family_to_text_dangling_event_ref():
    family = Family()
    family.set_gramps_id("F0000")
    family.set_handle("family-handle")
    event_ref = EventRef()
    event_ref.set_reference_handle("does-not-exist")
    family.set_event_ref_list([event_ref])
    public, private = family_to_text(family, DanglingDb())
    assert "F0000" in private
    assert "F0000" in public
