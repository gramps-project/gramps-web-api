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

"""Tests that ModifiedPrivateProxyDb backlinks do not reveal private references."""

import pytest
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db import DbTxn
from gramps.gen.db.utils import make_database
from gramps.gen.dbstate import DbState
from gramps.gen.lib import Event, EventRef, Media, MediaRef, Name, Note, Person

from gramps_webapi.api.resources.util import get_backlinks
from gramps_webapi.api.util import ModifiedPrivateProxyDb


@pytest.fixture(scope="module")
def db_handles():
    """Create a temporary SQLite DB with public objects referenced privately."""
    dbman = CLIDbManager(DbState())
    dirpath, db_name = dbman.create_new_db_cli("_test_priv_backlinks", dbid="sqlite")
    db = make_database("sqlite")
    db.load(dirpath)

    handles = {}

    with DbTxn("setup", db) as trans:
        handles["event"] = db.add_event(Event(), trans)
        handles["media"] = db.add_media(Media(), trans)
        handles["name_note"] = db.add_note(Note("note on a name"), trans)
        handles["person_note"] = db.add_note(Note("note on a person"), trans)

        # public person referencing everything through private references
        person = Person()
        event_ref = EventRef()
        event_ref.set_reference_handle(handles["event"])
        event_ref.set_privacy(True)
        person.add_event_ref(event_ref)
        media_ref = MediaRef()
        media_ref.set_reference_handle(handles["media"])
        media_ref.set_privacy(True)
        person.add_media_reference(media_ref)
        name = Name()
        name.set_first_name("Secret")
        name.set_privacy(True)
        name.add_note(handles["name_note"])
        person.add_alternate_name(name)
        handles["hidden_person"] = db.add_person(person, trans)

        # public person referencing the same objects publicly
        person = Person()
        event_ref = EventRef()
        event_ref.set_reference_handle(handles["event"])
        person.add_event_ref(event_ref)
        media_ref = MediaRef()
        media_ref.set_reference_handle(handles["media"])
        person.add_media_reference(media_ref)
        person.add_note(handles["person_note"])
        handles["public_person"] = db.add_person(person, trans)

        # private person referencing a public note
        person = Person()
        person.set_privacy(True)
        person.add_note(handles["person_note"])
        handles["private_person"] = db.add_person(person, trans)

    yield db, handles

    db.close()
    dbman.remove_database(db_name)


@pytest.fixture(scope="module")
def proxy(db_handles):
    """Return a ModifiedPrivateProxyDb wrapping the test db."""
    db, _handles = db_handles
    return ModifiedPrivateProxyDb(db)


def _backlink_handles(db, handle):
    return {ref_handle for _, ref_handle in db.find_backlink_handles(handle)}


@pytest.mark.parametrize("target", ["event", "media"])
def test_private_reference_hidden(db_handles, proxy, target):
    """A public person referencing an object privately is not a backlink."""
    db, handles = db_handles
    assert handles["hidden_person"] in _backlink_handles(db, handles[target])
    backlinks = _backlink_handles(proxy, handles[target])
    assert handles["hidden_person"] not in backlinks
    assert handles["public_person"] in backlinks


def test_note_on_private_name_hidden(db_handles, proxy):
    """A note on a private name does not reveal the person."""
    db, handles = db_handles
    assert handles["hidden_person"] in _backlink_handles(db, handles["name_note"])
    assert not _backlink_handles(proxy, handles["name_note"])


def test_private_object_hidden(db_handles, proxy):
    """A private person is not a backlink, a public one is."""
    _db, handles = db_handles
    backlinks = _backlink_handles(proxy, handles["person_note"])
    assert backlinks == {handles["public_person"]}


def test_include_classes(db_handles, proxy):
    """include_classes still restricts the result."""
    _db, handles = db_handles
    assert not list(proxy.find_backlink_handles(handles["event"], ["Family"]))
    assert list(proxy.find_backlink_handles(handles["event"], ["Person"])) == [
        ("Person", handles["public_person"])
    ]


def test_get_backlinks(db_handles, proxy):
    """The backlinks returned by the API are filtered."""
    _db, handles = db_handles
    assert get_backlinks(proxy, handles["media"]) == {
        "person": [handles["public_person"]]
    }
