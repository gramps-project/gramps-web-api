#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025       David Straub
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

"""Tests that ModifiedPrivateProxyDb.iter_*() does not leak private sub-references."""

import pytest
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.db import DbTxn
from gramps.gen.db.utils import make_database
from gramps.gen.dbstate import DbState
from gramps.gen.lib import (
    Citation,
    Event,
    EventRef,
    Family,
    Media,
    Name,
    Note,
    Person,
    Place,
    Repository,
    Source,
)

from gramps_webapi.api.util import ModifiedPrivateProxyDb


@pytest.fixture(scope="module")
def db_handles():
    """Create a temporary SQLite DB with objects containing private sub-references.

    Yields a dict of handles and the raw db, then tears down.
    """
    dbman = CLIDbManager(DbState())
    dirpath, db_name = dbman.create_new_db_cli("_test_priv_proxy", dbid="sqlite")
    db = make_database("sqlite")
    db.load(dirpath)

    handles = {}

    with DbTxn("setup", db) as trans:
        # --- Notes (top-level objects) ---
        private_note = Note("private note")
        private_note.set_privacy(True)
        handles["private_note"] = db.add_note(private_note, trans)

        public_note = Note("public note")
        public_note.set_privacy(False)
        handles["public_note"] = db.add_note(public_note, trans)

        # --- Place: has one private and one public note ref ---
        place = Place()
        place.set_name(place.get_name().__class__())
        place.get_name().set_value("Test Place")
        place.add_note(handles["private_note"])
        place.add_note(handles["public_note"])
        handles["place"] = db.add_place(place, trans)

        # --- Events (one private, one public) ---
        private_event = Event()
        private_event.set_privacy(True)
        private_event.add_note(handles["public_note"])
        handles["private_event"] = db.add_event(private_event, trans)

        public_event = Event()
        public_event.set_privacy(False)
        public_event.add_note(handles["private_note"])
        handles["public_event"] = db.add_event(public_event, trans)

        # --- Person: private alt name + event refs to private/public events ---
        person = Person()
        private_name = Name()
        private_name.set_first_name("Secret")
        private_name.set_privacy(True)
        person.add_alternate_name(private_name)
        public_name = Name()
        public_name.set_first_name("Visible")
        person.add_alternate_name(public_name)

        priv_eref = EventRef()
        priv_eref.set_reference_handle(handles["private_event"])
        person.add_event_ref(priv_eref)

        pub_eref = EventRef()
        pub_eref.set_reference_handle(handles["public_event"])
        person.add_event_ref(pub_eref)

        handles["person"] = db.add_person(person, trans)

        # --- Source: private and public note refs ---
        source = Source()
        source.add_note(handles["private_note"])
        source.add_note(handles["public_note"])
        handles["source"] = db.add_source(source, trans)

        # --- Citation: refs source above, has private note ---
        citation = Citation()
        citation.set_reference_handle(handles["source"])
        citation.add_note(handles["private_note"])
        citation.add_note(handles["public_note"])
        handles["citation"] = db.add_citation(citation, trans)

        # --- Repository: private and public note refs ---
        repo = Repository()
        repo.add_note(handles["private_note"])
        repo.add_note(handles["public_note"])
        handles["repository"] = db.add_repository(repo, trans)

        # --- Media: private note, public note, plus a checksum ---
        media = Media()
        media.set_checksum("abc123")
        media.add_note(handles["private_note"])
        media.add_note(handles["public_note"])
        handles["media"] = db.add_media(media, trans)

        # --- Family: event refs to private and public events ---
        family = Family()
        priv_fref = EventRef()
        priv_fref.set_reference_handle(handles["private_event"])
        family.add_event_ref(priv_fref)
        pub_fref = EventRef()
        pub_fref.set_reference_handle(handles["public_event"])
        family.add_event_ref(pub_fref)
        handles["family"] = db.add_family(family, trans)

    yield db, handles

    db.close()
    dbman.remove_database(db_name)


@pytest.fixture(scope="module")
def proxy(db_handles):
    """Return a ModifiedPrivateProxyDb wrapping the test db."""
    db, handles = db_handles
    return ModifiedPrivateProxyDb(db)


# ---------------------------------------------------------------------------
# iter_places
# ---------------------------------------------------------------------------


def test_iter_places_strips_private_note(db_handles, proxy):
    """Private note handle must not appear in place returned by iter_places()."""
    _db, handles = db_handles
    places = {p.handle: p for p in proxy.iter_places()}
    place = places[handles["place"]]
    assert handles["private_note"] not in place.get_note_list()


def test_iter_places_keeps_public_note(db_handles, proxy):
    """Public note handle must still appear in place returned by iter_places()."""
    _db, handles = db_handles
    places = {p.handle: p for p in proxy.iter_places()}
    place = places[handles["place"]]
    assert handles["public_note"] in place.get_note_list()


# ---------------------------------------------------------------------------
# iter_events
# ---------------------------------------------------------------------------


def test_iter_events_excludes_private_event(db_handles, proxy):
    """Private top-level event must not appear in iter_events()."""
    _db, handles = db_handles
    event_handles = {e.handle for e in proxy.iter_events()}
    assert handles["private_event"] not in event_handles


def test_iter_events_strips_private_note(db_handles, proxy):
    """Private note handle must not appear in public event returned by iter_events()."""
    _db, handles = db_handles
    events = {e.handle: e for e in proxy.iter_events()}
    event = events[handles["public_event"]]
    assert handles["private_note"] not in event.get_note_list()


# ---------------------------------------------------------------------------
# iter_people
# ---------------------------------------------------------------------------


def test_iter_people_strips_private_alternate_name(db_handles, proxy):
    """Private alternate name must not appear in person returned by iter_people()."""
    _db, handles = db_handles
    people = {p.handle: p for p in proxy.iter_people()}
    person = people[handles["person"]]
    alt_names = person.get_alternate_names()
    assert not any(n.get_privacy() for n in alt_names)
    visible_names = [n.get_first_name() for n in alt_names]
    assert "Secret" not in visible_names
    assert "Visible" in visible_names


def test_iter_people_strips_private_event_ref(db_handles, proxy):
    """Event ref to a private event must not appear in person returned by iter_people()."""
    _db, handles = db_handles
    people = {p.handle: p for p in proxy.iter_people()}
    person = people[handles["person"]]
    event_ref_handles = [r.get_reference_handle() for r in person.get_event_ref_list()]
    assert handles["private_event"] not in event_ref_handles
    assert handles["public_event"] in event_ref_handles


# ---------------------------------------------------------------------------
# iter_sources
# ---------------------------------------------------------------------------


def test_iter_sources_strips_private_note(db_handles, proxy):
    """Private note handle must not appear in source returned by iter_sources()."""
    _db, handles = db_handles
    sources = {s.handle: s for s in proxy.iter_sources()}
    source = sources[handles["source"]]
    assert handles["private_note"] not in source.get_note_list()
    assert handles["public_note"] in source.get_note_list()


# ---------------------------------------------------------------------------
# iter_citations
# ---------------------------------------------------------------------------


def test_iter_citations_strips_private_note(db_handles, proxy):
    """Private note handle must not appear in citation returned by iter_citations()."""
    _db, handles = db_handles
    citations = {c.handle: c for c in proxy.iter_citations()}
    citation = citations[handles["citation"]]
    assert handles["private_note"] not in citation.get_note_list()
    assert handles["public_note"] in citation.get_note_list()


# ---------------------------------------------------------------------------
# iter_repositories
# ---------------------------------------------------------------------------


def test_iter_repositories_strips_private_note(db_handles, proxy):
    """Private note handle must not appear in repository returned by iter_repositories()."""
    _db, handles = db_handles
    repos = {r.handle: r for r in proxy.iter_repositories()}
    repo = repos[handles["repository"]]
    assert handles["private_note"] not in repo.get_note_list()
    assert handles["public_note"] in repo.get_note_list()


# ---------------------------------------------------------------------------
# iter_media
# ---------------------------------------------------------------------------


def test_iter_media_strips_private_note(db_handles, proxy):
    """Private note handle must not appear in media returned by iter_media()."""
    _db, handles = db_handles
    media_objs = {m.handle: m for m in proxy.iter_media()}
    media = media_objs[handles["media"]]
    assert handles["private_note"] not in media.get_note_list()
    assert handles["public_note"] in media.get_note_list()


def test_iter_media_preserves_checksum(db_handles, proxy):
    """Checksum must be preserved in media returned by iter_media()."""
    _db, handles = db_handles
    media_objs = {m.handle: m for m in proxy.iter_media()}
    media = media_objs[handles["media"]]
    assert media.get_checksum() == "abc123"


# ---------------------------------------------------------------------------
# iter_families
# ---------------------------------------------------------------------------


def test_iter_families_strips_private_event_ref(db_handles, proxy):
    """Event ref to a private event must not appear in family returned by iter_families()."""
    _db, handles = db_handles
    families = {f.handle: f for f in proxy.iter_families()}
    family = families[handles["family"]]
    event_ref_handles = [r.get_reference_handle() for r in family.get_event_ref_list()]
    assert handles["private_event"] not in event_ref_handles
    assert handles["public_event"] in event_ref_handles


# ---------------------------------------------------------------------------
# iter_notes
# ---------------------------------------------------------------------------


def test_iter_notes_excludes_private_note(db_handles, proxy):
    """Private top-level note must not appear in iter_notes()."""
    _db, handles = db_handles
    note_handles = {n.handle for n in proxy.iter_notes()}
    assert handles["private_note"] not in note_handles


def test_iter_notes_includes_public_note(db_handles, proxy):
    """Public note must appear in iter_notes()."""
    _db, handles = db_handles
    note_handles = {n.handle for n in proxy.iter_notes()}
    assert handles["public_note"] in note_handles
