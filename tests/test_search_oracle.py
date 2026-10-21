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

"""Compare the search index with a brute-force search of the example tree.

The brute-force search reads the tree through the private proxy that the API
uses for a user without ViewPrivate, so it checks privacy independently of
the private flags stored in the index. Part of the tree is made private at random.

Run on SQLite, and also on PostgreSQL if `GRAMPSWEB_TEST_POSTGRES_URL` is set.
"""

from __future__ import annotations

import copy
import os
import random
import uuid

import pytest
from gramps.gen.db import DbTxn
from gramps.gen.lib import Name

from gramps_webapi.api.search.indexer import SearchIndexer
from gramps_webapi.api.search.query import Clause, Term, parse_query
from gramps_webapi.api.search.text import name_string, own_strings, tokenize
from gramps_webapi.api.util import ModifiedPrivateProxyDb
from gramps_webapi.const import GRAMPS_OBJECT_PLURAL, PRIMARY_GRAMPS_OBJECTS
from tests import ExampleDbInMemory

POSTGRES_URL = os.getenv("GRAMPSWEB_TEST_POSTGRES_URL")
BACKENDS = ["sqlite"] + (["postgresql"] if POSTGRES_URL else [])
EVENT_TYPES = ["birth", "death", "marriage", "burial"]


def _db_url(backend: str, tmp_path_factory) -> str:
    if backend == "sqlite":
        return f"sqlite:///{tmp_path_factory.mktemp('search')}/search.db"
    return POSTGRES_URL


def _make_private(db, rng: random.Random) -> None:
    """Make parts of the tree private, at random."""
    with DbTxn("make private", db) as trans:
        for person in list(db.iter_people()):
            draw = rng.random()
            if draw < 0.05:
                person.set_privacy(True)
            elif draw < 0.1:
                person.get_primary_name().set_privacy(True)
            for ref in person.get_event_ref_list():
                ref.set_privacy(rng.random() < 0.05)
                for attribute in ref.get_attribute_list():
                    attribute.set_privacy(rng.random() < 0.3)
            for attribute in person.get_attribute_list():
                attribute.set_privacy(rng.random() < 0.3)
            for name in person.get_alternate_names():
                name.set_privacy(rng.random() < 0.3)
            db.commit_person(person, trans)
        for family in list(db.iter_families()):
            family.set_privacy(rng.random() < 0.05)
            for ref in family.get_event_ref_list():
                ref.set_privacy(rng.random() < 0.1)
            db.commit_family(family, trans)
        for event in list(db.iter_events()):
            if rng.random() < 0.05:
                event.set_privacy(True)
                db.commit_event(event, trans)
        for media in list(db.iter_media()):
            if rng.random() < 0.2:
                media.set_privacy(True)
                db.commit_media(media, trans)
        for repository in list(db.iter_repositories()):
            if rng.random() < 0.2:
                repository.set_privacy(True)
                db.commit_repository(repository, trans)


def _is_placeholder(name: Name) -> bool:
    """Whether a name is what the private proxy shows instead of a private one."""
    surnames = [surname.surname for surname in name.get_surname_list()]
    return not name.first_name and surnames == ["Private"]


def oracle_docs(db, guest: bool) -> dict[str, list[list[str]]]:
    """Return the token lists each visible object can be found by."""
    view = ModifiedPrivateProxyDb(db) if guest else db
    docs: dict[str, list[list[str]]] = {}
    names: dict[str, list[str]] = {}
    for class_name in PRIMARY_GRAMPS_OBJECTS:
        for obj in view.method("iter_%s", GRAMPS_OBJECT_PLURAL[class_name])():
            if class_name == "Person":
                name = obj.get_primary_name()
                if guest and _is_placeholder(name):
                    obj = copy.deepcopy(obj)
                    obj.set_primary_name(Name())
                else:
                    names[obj.handle] = tokenize(name_string(name))
            docs[obj.handle] = [tokenize(own_strings(obj)[1])]

    def add_name(target: str, person_handle: str) -> None:
        if target in docs and person_handle in names:
            docs[target].append(names[person_handle])

    for person in view.iter_people():
        add_name(person.handle, person.handle)
        for ref in person.get_event_ref_list():
            if ref.get_role().is_primary():
                add_name(ref.ref, person.handle)
    for family in view.iter_families():
        parents = [h for h in (family.father_handle, family.mother_handle) if h]
        for parent in parents:
            add_name(family.handle, parent)
        for ref in family.get_event_ref_list():
            role = ref.get_role()
            if role.is_primary() or role.is_family():
                for parent in parents:
                    add_name(ref.ref, parent)
    return docs


def _term_in(term: Term, doc: list[str]) -> bool:
    n = len(term.tokens)
    for i in range(len(doc) - n + 1):
        window = doc[i : i + n]
        if term.prefix:
            if window[:-1] == list(term.tokens[:-1]) and window[-1].startswith(
                term.tokens[-1]
            ):
                return True
        elif window == list(term.tokens):
            return True
    return False


def oracle_search(docs: dict[str, list[list[str]]], clauses: list[Clause]) -> set:
    return {
        handle
        for handle, object_docs in docs.items()
        if all(
            any(_term_in(term, doc) for term in clause for doc in object_docs)
            for clause in clauses
        )
    }


def _queries(db, rng: random.Random) -> list[str]:
    names = [tokenize(name_string(p.get_primary_name())) for p in db.iter_people()]
    names = [name for name in names if len(name) >= 2]
    words = sorted({token for name in names for token in name})
    other = [tokenize(own_strings(obj)[1]) for obj in db.iter_notes()]
    other += [tokenize(own_strings(obj)[1]) for obj in db.iter_places()]
    other = [tokens for tokens in other if tokens]
    queries = [rng.choice(words) for _ in range(15)]
    queries += [" ".join(rng.choice(names)[:2]) for _ in range(10)]
    queries += ['"' + " ".join(rng.choice(names)[:2]) + '"' for _ in range(5)]
    queries += [rng.choice(words)[:3] + "*" for _ in range(5)]
    queries += [f"{rng.choice(words)} OR {rng.choice(words)}" for _ in range(5)]
    queries += [f"{rng.choice(EVENT_TYPES)} {rng.choice(words)}" for _ in range(10)]
    queries += [rng.choice(rng.choice(other)) for _ in range(10)]
    # words that are only in private parts of public objects
    hidden = set()
    for obj in db.iter_people():
        public, full = own_strings(obj)
        hidden |= set(tokenize(full)) - set(tokenize(public))
    queries += rng.sample(sorted(hidden), min(15, len(hidden)))
    # words on references, which are hidden with references to private objects
    on_references = set()
    for person in db.iter_people():
        for ref in person.get_event_ref_list() + person.get_media_list():
            for attribute in ref.get_attribute_list():
                on_references |= set(tokenize(attribute.get_value()))
        for person_ref in person.get_person_ref_list():
            on_references |= set(tokenize(person_ref.get_relation()))
    for source in db.iter_sources():
        for repo_ref in source.get_reporef_list():
            on_references |= set(tokenize(repo_ref.get_call_number()))
    queries += rng.sample(sorted(on_references), min(15, len(on_references)))
    return queries


def _mismatches(indexer, docs, queries, guest: bool) -> list[str]:
    result = []
    for query in queries:
        _, hits = indexer.search(
            query, page=1, pagesize=100000, include_private=not guest
        )
        got = {hit["handle"] for hit in hits}
        want = oracle_search(docs, parse_query(query))
        if got != want:
            result.append(
                f"{query!r}: {len(got)} hits, expected {len(want)};"
                f" unexpected {sorted(got - want)[:3]}, missing {sorted(want - got)[:3]}"
            )
    return result


@pytest.fixture(scope="module")
def tree():
    """The example tree with private data, and the oracle's documents."""
    db = ExampleDbInMemory().load()
    _make_private(db, random.Random(1))
    yield {
        "db": db,
        "docs": {guest: oracle_docs(db, guest) for guest in (False, True)},
        "queries": _queries(db, random.Random(2)),
    }
    db.close()


@pytest.fixture(scope="module", params=BACKENDS)
def indexer(request, tree, tmp_path_factory):
    indexer = SearchIndexer(
        tree=f"oracle-{uuid.uuid4().hex}",
        db_url=_db_url(request.param, tmp_path_factory),
    )
    indexer.reindex_full(tree["db"])
    yield indexer
    indexer._delete_all()


@pytest.mark.parametrize("guest", [False, True], ids=["owner", "guest"])
def test_search_matches_oracle(tree, indexer, guest):
    mismatches = _mismatches(indexer, tree["docs"][guest], tree["queries"], guest=guest)
    assert not mismatches, "\n".join(mismatches)


def _dump(indexer: SearchIndexer) -> dict[str, list]:
    """All rows of a tree's index, without the tree and row IDs."""
    queries = {
        "obj": "SELECT handle, obj_type, private, change FROM search_obj",
        "doc": "SELECT handle, kind, variant, private, content FROM search_doc",
        "ref": "SELECT from_handle, to_handle, kind, private FROM search_ref",
    }
    import sqlalchemy as sa

    with indexer.engine.connect() as conn:
        return {
            key: sorted(
                tuple(row)
                for row in conn.execute(
                    sa.text(f"{sql} WHERE tree = :tree"), {"tree": indexer.tree}
                )
            )
            for key, sql in queries.items()
        }


def _edit(db, rng: random.Random) -> list[tuple[str, str]]:
    """Change the tree as users would; return the (class, handle) touched."""
    touched = []
    with DbTxn("edit", db) as trans:
        people = list(db.iter_people())
        for i, person in enumerate(rng.sample(people, 40)):
            if i % 2:
                person.get_primary_name().set_first_name(f"Zqrenamed{i}")
            else:
                person.set_privacy(not person.private)
            for ref in person.get_event_ref_list()[:1]:
                ref.set_privacy(not ref.private)
            db.commit_person(person, trans)
            touched.append(("Person", person.handle))
        for family in rng.sample(list(db.iter_families()), 10):
            family.set_privacy(not family.private)
            db.commit_family(family, trans)
            touched.append(("Family", family.handle))
        # delete events with the references to them, as the API does
        for event in rng.sample(list(db.iter_events()), 5):
            for class_name, handle in list(db.find_backlink_handles(event.handle)):
                if class_name == "Person":
                    obj = db.get_person_from_handle(handle)
                elif class_name == "Family":
                    obj = db.get_family_from_handle(handle)
                else:
                    continue
                obj.set_event_ref_list(
                    [r for r in obj.get_event_ref_list() if r.ref != event.handle]
                )
                if class_name == "Person":
                    db.commit_person(obj, trans)
                else:
                    db.commit_family(obj, trans)
                touched.append((class_name, handle))
            db.remove_event(event.handle, trans)
            touched.append(("Event", event.handle))
    return touched


@pytest.mark.parametrize("backend", BACKENDS)
def test_updates_match_full_rebuild(backend, tmp_path_factory):
    """Incremental and per-object updates give the same index as a rebuild."""
    db = ExampleDbInMemory().load()
    _make_private(db, random.Random(3))
    url = _db_url(backend, tmp_path_factory)
    incremental, per_object, rebuilt = (
        SearchIndexer(tree=f"{name}-{uuid.uuid4().hex}", db_url=url)
        for name in ("incremental", "per-object", "rebuilt")
    )
    try:
        incremental.reindex_full(db)
        per_object.reindex_full(db)
        touched = _edit(db, random.Random(4))
        incremental.reindex_incremental(db)
        # as the task indexing a transaction does
        for class_name, handle in dict.fromkeys(touched):
            per_object.add_or_update_object(handle, db, class_name)
        rebuilt.reindex_full(db)
        expected = _dump(rebuilt)
        assert _dump(incremental) == expected
        assert _dump(per_object) == expected
        # and the result is still what the oracle finds
        queries = [f"zqrenamed{i}" for i in range(1, 40, 2)] + _queries(
            db, random.Random(5)
        )
        for guest in (False, True):
            mismatches = _mismatches(
                incremental, oracle_docs(db, guest), queries, guest=guest
            )
            assert not mismatches, "\n".join(mismatches)
    finally:
        for indexer in (incremental, per_object, rebuilt):
            indexer._delete_all()
        db.close()
