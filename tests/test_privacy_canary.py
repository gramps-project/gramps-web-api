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

"""Privacy canary test: private data must not reach users without ViewPrivate.

Unique tokens are planted in private objects, private parts of public objects,
and private references between public objects. The API is then crawled as a
guest (no ViewPrivate permission) and as an owner. Every token must show up for
the owner (otherwise the test does not reach it) and never for the guest.

The test does not know how privacy is implemented, so it also covers code
paths added later.
"""

from __future__ import annotations

import gzip
import io
import json
import os
import string
import zipfile
from dataclasses import dataclass, field
from itertools import product
from unittest.mock import patch

import pytest
from gramps.gen.db import DbTxn
from gramps.gen.db.utils import open_database
from gramps.gen.lib import (
    Address,
    Attribute,
    AttributeType,
    ChildRef,
    Citation,
    Date,
    Event,
    EventRef,
    EventRoleType,
    EventType,
    Family,
    Media,
    MediaRef,
    Name,
    Note,
    Person,
    PersonRef,
    Place,
    PlaceName,
    RepoRef,
    Repository,
    Source,
    SrcAttribute,
    Surname,
    Url,
)

from gramps_webapi.api.search import get_search_indexer
from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import (
    ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS,
    ROLE_GUEST,
    ROLE_OWNER,
)
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EXAMPLE_GRAMPS_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager
from tests import ExampleDbSQLite

TREE_NAME = "privacy_canary"
USERS = {
    ROLE_OWNER: ("canary_owner", "owner-pw"),
    ROLE_GUEST: ("canary_guest", "guest-pw"),
}
PLURAL = {
    "Person": "people",
    "Family": "families",
    "Event": "events",
    "Place": "places",
    "Citation": "citations",
    "Source": "sources",
    "Repository": "repositories",
    "Media": "media",
    "Note": "notes",
}
FULL_PARAMS = ["?extend=all&profile=all&backlinks=true", "?extend=all", ""]
# Leaks that are known and will be fixed when search and permissions are
# redesigned, as prefixes of the reported leaks.
KNOWN_LEAKS = (
    # custom type lists are collected from all objects, private or not
    "custom type of a private attribute: GET /api/types/",
    "custom type of a private citation attribute: GET /api/types/",
    "private event's custom type: GET /api/types/",
)
AGGREGATE_URLS = [
    "/api/metadata/?surnames=true",
    "/api/types/",
    "/api/types/custom/",
    "/api/facts/",
    "/api/anniversaries.ics",
    "/api/places/coordinates/",
    "/api/timelines/people/",
    "/api/timelines/families/",
    "/api/name-groups/",
    "/api/tags/",
    "/api/bookmarks/",
]


@dataclass
class Canaries:
    """What was planted in the tree."""

    # token -> where it was planted
    tokens: dict[str, str] = field(default_factory=dict)
    # (description, class, handle) of objects whose endpoints are crawled
    objects: list[tuple[str, str]] = field(default_factory=list)
    private_objects: list[tuple[str, str]] = field(default_factory=list)
    # (description, class_a, handle_a, class_b, handle_b): a and b are only
    # connected through a private reference
    edges: list[tuple[str, str, str, str, str]] = field(default_factory=list)
    # (description, query, handle): searching for the query finds the object
    # only through a private connection
    search_edges: list[tuple[str, str, str]] = field(default_factory=list)
    person_pairs: list[tuple[str, str]] = field(default_factory=list)
    _letters: object = None
    _public_letters: object = None

    def token(self, description: str) -> str:
        """Return a new unique token (letters only, so tokenizers keep it whole)."""
        if self._letters is None:
            self._letters = product(string.ascii_lowercase, repeat=3)
        token = "zqprv" + "".join(next(self._letters))
        self.tokens[token] = description
        return token

    def word(self) -> str:
        """Return a new unique word for public text, unlike a token."""
        if self._public_letters is None:
            self._public_letters = product(string.ascii_lowercase, repeat=3)
        return "zqpub" + "".join(next(self._public_letters))


def _name(first: str, surname: str = "Canary") -> Name:
    name = Name()
    name.set_first_name(first)
    surname_obj = Surname()
    surname_obj.set_surname(surname)
    name.add_surname(surname_obj)
    return name


def _person(db, trans, first: str, private: bool = False) -> Person:
    person = Person()
    person.set_primary_name(_name(first))
    person.set_privacy(private)
    db.add_person(person, trans)
    return person


def _attribute(value: str, private: bool = False, type_name: str = "") -> Attribute:
    attribute = Attribute()
    if type_name:
        attribute.set_type((AttributeType.CUSTOM, type_name))
    else:
        attribute.set_type(AttributeType.DESCRIPTION)
    attribute.set_value(value)
    attribute.set_privacy(private)
    return attribute


def _plant(db) -> Canaries:
    """Add canary data to the example tree."""
    c = Canaries()
    with DbTxn("plant canaries", db) as trans:
        # --- private primary objects ---
        person = Person()
        person.set_primary_name(
            _name(
                c.token("private person's given name"),
                surname=c.token("private person's surname"),
            )
        )
        person.set_privacy(True)
        db.add_person(person, trans)
        c.private_objects.append(("Person", person.handle))

        family = Family()
        family.add_attribute(_attribute(c.token("private family's attribute")))
        family.set_privacy(True)
        db.add_family(family, trans)
        c.private_objects.append(("Family", family.handle))

        event = Event()
        event.set_type((EventType.CUSTOM, c.token("private event's custom type")))
        event.set_description(c.token("private event's description"))
        event.set_privacy(True)
        db.add_event(event, trans)
        c.private_objects.append(("Event", event.handle))

        place = Place()
        place_name = PlaceName()
        place_name.set_value(c.token("private place's name"))
        place.set_name(place_name)
        place.set_privacy(True)
        db.add_place(place, trans)
        c.private_objects.append(("Place", place.handle))

        source = Source()
        source.set_title(c.token("private source's title"))
        source.set_privacy(True)
        db.add_source(source, trans)
        c.private_objects.append(("Source", source.handle))

        citation = Citation()
        citation.set_page(c.token("private citation's page"))
        citation.set_privacy(True)
        db.add_citation(citation, trans)
        c.private_objects.append(("Citation", citation.handle))

        repository = Repository()
        repository.set_name(c.token("private repository's name"))
        repository.set_privacy(True)
        db.add_repository(repository, trans)
        c.private_objects.append(("Repository", repository.handle))

        note = Note(c.token("private note's text"))
        note.set_privacy(True)
        db.add_note(note, trans)
        c.private_objects.append(("Note", note.handle))

        media = Media()
        media.set_description(c.token("private media's description"))
        media.set_privacy(True)
        db.add_media(media, trans)
        c.private_objects.append(("Media", media.handle))

        # --- private parts of a public person ---
        holder = _person(db, trans, "Holder")
        name = _name(c.token("private alternate name"))
        name.set_privacy(True)
        holder.add_alternate_name(name)
        holder.add_attribute(_attribute(c.token("private attribute"), private=True))
        holder.add_attribute(
            _attribute(
                "x",
                private=True,
                type_name=c.token("custom type of a private attribute"),
            )
        )
        address = Address()
        address.set_street(c.token("private address"))
        address.set_privacy(True)
        holder.add_address(address)
        url = Url()
        url.set_path("https://example.org/" + c.token("private web link"))
        url.set_privacy(True)
        holder.add_url(url)
        public_event = Event()
        public_event.set_type(EventType.RESIDENCE)
        db.add_event(public_event, trans)
        event_ref = EventRef()
        event_ref.set_reference_handle(public_event.handle)
        event_ref.add_attribute(
            _attribute(c.token("private attribute of an event reference"), True)
        )
        holder.add_event_ref(event_ref)
        db.commit_person(holder, trans)
        c.objects += [("Person", holder.handle), ("Event", public_event.handle)]

        # public person with a private primary name
        hidden_name = _person(db, trans, c.token("private primary name"))
        hidden_name.get_primary_name().set_privacy(True)
        db.commit_person(hidden_name, trans)
        c.objects.append(("Person", hidden_name.handle))

        # --- a private person in a public family and a public event ---
        father = _person(db, trans, c.token("private father of a public family"), True)
        child = _person(db, trans, "Child")
        public_family = Family()
        public_family.set_father_handle(father.handle)
        child_ref = ChildRef()
        child_ref.set_reference_handle(child.handle)
        public_family.add_child_ref(child_ref)
        db.add_family(public_family, trans)
        father.add_family_handle(public_family.handle)
        child.add_parent_family_handle(public_family.handle)
        participant = _person(
            db, trans, c.token("private participant of a public event"), True
        )
        shared_event = Event()
        shared_event.set_type(EventType.BIRTH)
        date = Date()
        date.set_yr_mon_day(1950, 5, 17)
        shared_event.set_date_object(date)  # so it shows up in calendars
        db.add_event(shared_event, trans)
        event_ref = EventRef()
        event_ref.set_reference_handle(shared_event.handle)
        participant.add_event_ref(event_ref)
        for obj in (father, child, participant):
            db.commit_person(obj, trans)
        c.objects += [
            ("Family", public_family.handle),
            ("Person", child.handle),
            ("Event", shared_event.handle),
        ]
        c.private_objects += [("Person", father.handle), ("Person", participant.handle)]

        # --- public objects connected only through private references ---
        def edge(description, referrer, target_class, target_handle):
            c.edges.append(
                (
                    description,
                    referrer.__class__.__name__,
                    referrer.handle,
                    target_class,
                    target_handle,
                )
            )
            c.objects += [
                (referrer.__class__.__name__, referrer.handle),
                (target_class, target_handle),
            ]

        target_event = Event()
        target_event.set_type(EventType.DEATH)
        db.add_event(target_event, trans)
        ref_note = Note("public note on a private event reference")
        db.add_note(ref_note, trans)
        word = c.word()
        referrer = _person(db, trans, word)
        event_ref = EventRef()
        event_ref.set_reference_handle(target_event.handle)
        event_ref.add_note(ref_note.handle)
        event_ref.set_privacy(True)
        referrer.add_event_ref(event_ref)
        db.commit_person(referrer, trans)
        edge("private event reference", referrer, "Event", target_event.handle)
        c.search_edges.append(
            ("participant through a private event reference", word, target_event.handle)
        )
        edge("note on a private event reference", referrer, "Note", ref_note.handle)

        target_media = Media()
        target_media.set_description("public media")
        db.add_media(target_media, trans)
        referrer = _person(db, trans, "MediaReferrer")
        media_ref = MediaRef()
        media_ref.set_reference_handle(target_media.handle)
        media_ref.set_privacy(True)
        referrer.add_media_reference(media_ref)
        db.commit_person(referrer, trans)
        edge("private media reference", referrer, "Media", target_media.handle)

        associate = _person(db, trans, "Associate")
        referrer = _person(db, trans, "AssociationReferrer")
        person_ref = PersonRef()
        person_ref.set_reference_handle(associate.handle)
        person_ref.set_relation("Godfather")
        person_ref.set_privacy(True)
        referrer.add_person_ref(person_ref)
        db.commit_person(referrer, trans)
        edge("private association", referrer, "Person", associate.handle)

        name_note = Note("public note on a private name")
        db.add_note(name_note, trans)
        name_citation = Citation()
        name_citation.set_page("public citation on a private name")
        db.add_citation(name_citation, trans)
        referrer = _person(db, trans, "NameReferrer")
        name = _name("Hidden")
        name.set_privacy(True)
        name.add_note(name_note.handle)
        name.add_citation(name_citation.handle)
        referrer.add_alternate_name(name)
        db.commit_person(referrer, trans)
        edge("note on a private name", referrer, "Note", name_note.handle)
        edge("citation on a private name", referrer, "Citation", name_citation.handle)

        parent = _person(db, trans, "Parent")
        adopted = _person(db, trans, "PrivateChild")
        family = Family()
        family.set_father_handle(parent.handle)
        child_ref = ChildRef()
        child_ref.set_reference_handle(adopted.handle)
        child_ref.set_privacy(True)
        family.add_child_ref(child_ref)
        db.add_family(family, trans)
        parent.add_family_handle(family.handle)
        adopted.add_parent_family_handle(family.handle)
        db.commit_person(parent, trans)
        db.commit_person(adopted, trans)
        edge("private child reference", family, "Person", adopted.handle)
        c.person_pairs.append((parent.handle, adopted.handle))

        target_repository = Repository()
        target_repository.set_name("public repository")
        db.add_repository(target_repository, trans)
        referrer = Source()
        referrer.set_title("RepositoryReferrer")
        repo_ref = RepoRef()
        repo_ref.set_reference_handle(target_repository.handle)
        repo_ref.set_privacy(True)
        referrer.add_repo_reference(repo_ref)
        db.add_source(referrer, trans)
        edge(
            "private repository reference",
            referrer,
            "Repository",
            target_repository.handle,
        )

        citation = Citation()
        citation.set_page("public citation")
        attribute = SrcAttribute()
        attribute.set_type(c.token("custom type of a private citation attribute"))
        attribute.set_value(c.token("private citation attribute"))
        attribute.set_privacy(True)
        citation.add_attribute(attribute)
        db.add_citation(citation, trans)
        c.objects.append(("Citation", citation.handle))

        # --- names copied into the search text of families and events ---
        def family_event(father, private_family=False, private_ref=False) -> Event:
            """Add a family of `father` taking part in a new public event."""
            event = Event()
            event.set_type(EventType.MARRIAGE)
            db.add_event(event, trans)
            event_ref = EventRef()
            event_ref.set_reference_handle(event.handle)
            event_ref.set_role(EventRoleType.FAMILY)
            event_ref.set_privacy(private_ref)
            family = Family()
            family.set_father_handle(father.handle)
            family.add_event_ref(event_ref)
            family.set_privacy(private_family)
            db.add_family(family, trans)
            father.add_family_handle(family.handle)
            db.commit_person(father, trans)
            if private_family:
                c.private_objects.append(("Family", family.handle))
            else:
                c.objects.append(("Family", family.handle))
            c.objects.append(("Event", event.handle))
            return event

        word = c.word()
        event = family_event(_person(db, trans, word), private_family=True)
        c.search_edges.append(("family event of a private family", word, event.handle))

        word = c.word()
        event = family_event(_person(db, trans, word), private_ref=True)
        c.search_edges.append(
            (
                "family event through a private family event reference",
                word,
                event.handle,
            )
        )

        father = _person(
            db,
            trans,
            c.token("private father of a family taking part in a public event"),
            True,
        )
        family_event(father)
        c.private_objects.append(("Person", father.handle))

        father = _person(
            db, trans, c.token("private primary name of a public family's father")
        )
        father.get_primary_name().set_privacy(True)
        family_event(father)
        c.objects.append(("Person", father.handle))

        participant = _person(
            db, trans, c.token("private primary name of a public event's participant")
        )
        participant.get_primary_name().set_privacy(True)
        event = Event()
        event.set_type(EventType.DEATH)
        db.add_event(event, trans)
        event_ref = EventRef()
        event_ref.set_reference_handle(event.handle)
        participant.add_event_ref(event_ref)
        db.commit_person(participant, trans)
        c.objects += [("Person", participant.handle), ("Event", event.handle)]

        # --- text on public references to private objects, which the
        # private proxy hides together with the reference ---
        private = {}
        for class_name, handle in c.private_objects:
            private.setdefault(class_name, handle)
        holder = _person(db, trans, "ReferenceHolder")
        event_ref = EventRef()
        event_ref.set_reference_handle(private["Event"])
        event_ref.add_attribute(
            _attribute(c.token("attribute of a reference to a private event"))
        )
        holder.add_event_ref(event_ref)
        media_ref = MediaRef()
        media_ref.set_reference_handle(private["Media"])
        media_ref.add_attribute(
            _attribute(c.token("attribute of a reference to private media"))
        )
        holder.add_media_reference(media_ref)
        person_ref = PersonRef()
        person_ref.set_reference_handle(private["Person"])
        person_ref.set_relation(c.token("association with a private person"))
        holder.add_person_ref(person_ref)
        db.commit_person(holder, trans)
        source = Source()
        source.set_title("ReferenceHolder source")
        repo_ref = RepoRef()
        repo_ref.set_reference_handle(private["Repository"])
        repo_ref.set_call_number(c.token("call number at a private repository"))
        source.add_repo_reference(repo_ref)
        db.add_source(source, trans)
        c.objects += [("Person", holder.handle), ("Source", source.handle)]

    return c


@pytest.fixture(scope="module")
def crawl():
    """Plant canaries, then crawl the API as owner and as guest."""
    ExampleDbSQLite(name=TREE_NAME)
    db = open_database(TREE_NAME, force_unlock=True)
    canaries = _plant(db)
    db.close()

    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EXAMPLE_GRAMPS_AUTH_CONFIG}):
        app = create_app(
            config={
                "TESTING": True,
                # record crashes as 500 responses instead of aborting the crawl
                "PROPAGATE_EXCEPTIONS": False,
                "RATELIMIT_ENABLED": False,
                "MEDIA_BASE_DIR": f"{os.environ['GRAMPS_RESOURCES']}/doc/gramps/example/gramps",
            },
            config_from_env=False,
        )
    client = app.test_client()
    with app.app_context():
        user_db.create_all()
        db_manager = WebDbManager(name=TREE_NAME, create_if_missing=False)
        tree = db_manager.dirname
        for role, (name, password) in USERS.items():
            add_user(name=name, password=password, role=role, tree=tree)
        db_state = db_manager.get_db()
        get_search_indexer(tree).reindex_full(db_state.db)
        db_state.db.close()

    results = {}
    for role, (name, password) in USERS.items():
        rv = client.post("/api/token/", json={"username": name, "password": password})
        headers = {"Authorization": f"Bearer {rv.json['access_token']}"}
        results[role] = _crawl(client, headers, canaries)
    yield canaries, results[ROLE_OWNER], results[ROLE_GUEST]


def _body(data: bytes) -> str:
    """Response body as text, unpacking compressed exports."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    elif data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            data = b"".join(archive.read(name) for name in archive.namelist())
    return data.decode("utf-8", errors="replace")


def _crawl(client, headers, canaries: Canaries) -> dict[str, tuple[int, str]]:
    """Return {url: (status, body)} for all crawled URLs."""
    results: dict[str, tuple[int, str]] = {}

    def get(url: str, param_options=("",)) -> None:
        for params in param_options:
            rv = client.get(url + params, headers=headers)
            if rv.status_code != 422:
                break
        results[url] = (rv.status_code, _body(rv.data))

    for class_name, handle in set(canaries.objects + canaries.private_objects):
        base = f"/api/{PLURAL[class_name]}/{handle}"
        get(base, FULL_PARAMS)
        if class_name == "Person":
            for suffix in ("/timeline", "/dna/matches", "/ydna"):
                get(base + suffix)
            get(f"/api/living/{handle}")
            get(f"/api/living/{handle}/dates")
        if class_name == "Family":
            get(base + "/timeline")
    for plural in PLURAL.values():
        get(f"/api/{plural}/", ["?extend=all&backlinks=true", ""])
    rv = client.post(
        f"/api/users/-/access-tokens/{ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS}/",
        headers=headers,
    )
    calendar_params = (
        f"?token={rv.json['token']}&event_types=all&living_only=false"
        "&primary_participants_only=false"
    )
    for url in AGGREGATE_URLS:
        get(url, [calendar_params] if url == "/api/anniversaries.ics" else [""])
    for query in [*canaries.tokens, *(q for _, q, _ in canaries.search_edges)]:
        get(f"/api/search/?query={query}")
    for handle1, handle2 in canaries.person_pairs:
        get(f"/api/relations/{handle1}/{handle2}")
        get(f"/api/relations/{handle1}/{handle2}/all")
    rv = client.get("/api/exporters/", headers=headers)
    for exporter in rv.json or []:
        get(f"/api/exporters/{exporter['extension']}/file", ["?compress=0&private=0"])
    return results


def _search_hits(response: tuple[int, str]) -> bool:
    status, body = response
    assert status == 200, f"search failed with {status}: {body[:200]}"
    return body.strip() != "[]"


def test_no_server_errors(crawl):
    """No crawled URL crashes, e.g. on a private object that the proxy hides."""
    _canaries, owner, guest = crawl
    errors = [
        f"{who}: GET {url} returned {status}"
        for who, results in (("owner", owner), ("guest", guest))
        for url, (status, _body) in results.items()
        if status >= 500
    ]
    assert not errors, "\n".join(sorted(errors))


def test_aggregate_urls_reachable(crawl):
    """Coverage check: a failing aggregate URL would hide leaks."""
    _canaries, owner, guest = crawl
    failing = [
        f"{who}: GET {url} returned {results[url][0]}"
        for who, results in (("owner", owner), ("guest", guest))
        for url in AGGREGATE_URLS
        if results[url][0] != 200
    ]
    assert not failing, "\n".join(failing)


def test_owner_sees_every_canary(crawl):
    """Positive control: every planted token is reachable at all."""
    canaries, owner, _guest = crawl
    unreached = [
        f"{token} ({description})"
        for token, description in canaries.tokens.items()
        if not any(token in body for _status, body in owner.values())
    ]
    assert not unreached, "Not reached by the crawl:\n" + "\n".join(unreached)


def _check_leaks(leaks: list[str], known: tuple[str, ...], title: str) -> None:
    """Fail on leaks that are not known, and on known leaks that are fixed."""
    unexpected = [leak for leak in leaks if not leak.startswith(known)]
    fixed = [prefix for prefix in known if not any(l.startswith(prefix) for l in leaks)]
    assert not unexpected, f"{title}:\n" + "\n".join(sorted(unexpected))
    assert not fixed, "Fixed, remove from the known leaks:\n" + "\n".join(fixed)


def test_guest_sees_no_canary(crawl):
    """No private text reaches a user without ViewPrivate."""
    canaries, _owner, guest = crawl
    leaks = []
    for url, (status, body) in guest.items():
        if url.startswith("/api/search/"):
            continue
        for token, description in canaries.tokens.items():
            if token in body:
                leaks.append(f"{description}: GET {url} ({status})")
    _check_leaks(leaks, KNOWN_LEAKS, "Private text leaked")


def test_guest_search_finds_no_canary(crawl):
    """Searching for private text finds nothing for a user without ViewPrivate."""
    canaries, _owner, guest = crawl
    leaks = [
        f"{description}: search for {token} returns hits"
        for token, description in canaries.tokens.items()
        if _search_hits(guest[f"/api/search/?query={token}"])
    ]
    assert not leaks, "Search reveals private text:\n" + "\n".join(sorted(leaks))


def _search_handles(response: tuple[int, str]) -> set[str]:
    status, body = response
    assert status == 200, f"search failed with {status}: {body[:200]}"
    return {hit["handle"] for hit in json.loads(body)}


def test_guest_search_respects_private_connections(crawl):
    """Searching finds no object that matches only through private data."""
    canaries, owner, guest = crawl
    leaks, unreached = [], []
    for description, query, handle in canaries.search_edges:
        url = f"/api/search/?query={query}"
        if handle not in _search_handles(owner[url]):
            unreached.append(description)
        if handle in _search_handles(guest[url]):
            leaks.append(f"{description}: search for {query} finds {handle}")
    assert not unreached, "Positive control failed for:\n" + "\n".join(unreached)
    assert not leaks, "Search reveals private connections:\n" + "\n".join(leaks)


def test_guest_cannot_fetch_private_objects(crawl):
    """Private objects are not found for a user without ViewPrivate."""
    canaries, _owner, guest = crawl
    found = [
        f"GET /api/{PLURAL[class_name]}/{handle} returned {guest[url][0]}"
        for class_name, handle in canaries.private_objects
        if guest[(url := f"/api/{PLURAL[class_name]}/{handle}")][0] < 400
    ]
    assert not found, "\n".join(found)


def test_private_references_hidden(crawl):
    """Objects connected only through a private reference look unconnected."""
    canaries, owner, guest = crawl
    leaks, unreached = [], []
    for description, class_a, handle_a, class_b, handle_b in canaries.edges:
        for class_name, handle, other in [
            (class_a, handle_a, handle_b),
            (class_b, handle_b, handle_a),
        ]:
            url = f"/api/{PLURAL[class_name]}/{handle}"
            if other in guest[url][1]:
                leaks.append(f"{description}: GET {url} reveals the connection")
        if (
            handle_b not in owner[f"/api/{PLURAL[class_a]}/{handle_a}"][1]
            and handle_a not in owner[f"/api/{PLURAL[class_b]}/{handle_b}"][1]
        ):
            unreached.append(description)
    assert not unreached, "Positive control failed for:\n" + "\n".join(unreached)
    assert not leaks, "Private references leaked:\n" + "\n".join(leaks)
