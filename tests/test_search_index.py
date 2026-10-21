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

"""Tests for the full-text search index, on small hand-made trees.

Run on SQLite, and also on PostgreSQL if `GRAMPSWEB_TEST_POSTGRES_URL` is set.
"""

from __future__ import annotations

import os
import sqlite3
import uuid

import pytest

from gramps_webapi.api.search import schema
from gramps_webapi.api.search.indexer import SearchIndexer
from gramps_webapi.api.search.query import Term, parse_query
from gramps_webapi.api.search.schema import get_engine
from gramps_webapi.api.search.text import ObjectRows, tokenize

POSTGRES_URL = os.getenv("GRAMPSWEB_TEST_POSTGRES_URL")
BACKENDS = ["sqlite"] + (["postgresql"] if POSTGRES_URL else [])


@pytest.fixture(params=BACKENDS)
def indexer(request, tmp_path):
    """An empty index of a new tree."""
    if request.param == "sqlite":
        url = f"sqlite:///{tmp_path}/search.db"
    else:
        url = POSTGRES_URL
    # a new tree each time, since PostgreSQL tests share the database
    indexer = SearchIndexer(tree=f"test-{uuid.uuid4().hex}", db_url=url)
    yield indexer
    indexer._delete_all()


def _doc(text, variant="all", private=False, kind="own"):
    return (kind, variant, private, " ".join(tokenize(text)))


def person(handle, name, private=False, name_private=False, events=(), text=""):
    """A person; `events` are (event handle, private reference) pairs."""
    docs = []
    if private:
        docs.append(_doc(f"{handle} {name} {text}", "full", True))
    elif name_private:
        docs.append(_doc(f"{handle} {name} {text}", "full"))
        docs.append(_doc(f"{handle} {text}", "redacted"))
    else:
        docs.append(_doc(f"{handle} {name} {text}"))
    docs.append(_doc(name, private=name_private, kind="name"))
    refs = [(event, "participant", ref_private) for event, ref_private in events]
    return ObjectRows(handle, "person", private, 1.0, docs, refs)


def family(handle, parents=(), events=(), private=False):
    """A family; `events` are (event handle, private reference) pairs."""
    refs = [(parent, "parent", False) for parent in parents]
    refs += [(event, "participant", ref_private) for event, ref_private in events]
    docs = [_doc(handle, "full" if private else "all", private)]
    return ObjectRows(handle, "family", private, 2.0, docs, refs)


def event(handle, text, private=False, change=3.0):
    docs = [_doc(f"{handle} {text}", "full" if private else "all", private)]
    return ObjectRows(handle, "event", private, change, docs)


def found(indexer, query, guest=False, **kwargs) -> set[str]:
    _, hits = indexer.search(
        query, page=1, pagesize=1000, include_private=not guest, **kwargs
    )
    return {hit["handle"] for hit in hits}


def test_parse_query():
    word = lambda *tokens: Term(tokens)  # noqa: E731
    assert parse_query("a OR b c") == [(word("a"), word("b")), (word("c"),)]
    assert parse_query("a AND b") == [(word("a"),), (word("b"),)]
    assert parse_query('"John Smith"') == [(word("john", "smith"),)]
    assert parse_query("O'Brien") == [(word("o", "brien"),)]
    assert parse_query("smi*") == [(Term(("smi",), prefix=True),)]
    assert parse_query("Müller") == [(word("müller"), word("muller"))]
    assert parse_query("OR !!! *") == []


def test_family_and_events_found_by_names(indexer):
    indexer._add_objects(
        [
            person("I1", "John Smith", events=[("E1", False)]),
            person("I2", "Mary Jones"),
            family("F1", parents=["I1", "I2"], events=[("E2", False)]),
            event("E1", "birth"),
            event("E2", "marriage"),
        ]
    )
    assert found(indexer, "smith") == {"I1", "F1", "E1", "E2"}
    # clauses can be matched by different documents of the same object
    assert found(indexer, "john mary") == {"F1", "E2"}
    assert found(indexer, "birth smith") == {"E1"}
    assert found(indexer, "marriage jones") == {"E2"}
    # phrases match within one document
    assert found(indexer, '"smith mary"') == set()


@pytest.mark.parametrize(
    "rows, guest_finds",
    [
        (
            [
                person("I1", "John Smith", private=True, events=[("E1", False)]),
                family("F1", parents=["I1"], events=[("E2", False)]),
            ],
            set(),
        ),
        (
            [
                person("I1", "John Smith", name_private=True, events=[("E1", False)]),
                family("F1", parents=["I1"], events=[("E2", False)]),
            ],
            set(),
        ),
        (
            [
                person("I1", "John Smith", events=[("E1", True)]),
                family("F1", parents=["I1"], events=[("E2", False)], private=True),
            ],
            {"I1"},
        ),
        (
            [
                person("I1", "John Smith", events=[("E1", True)]),
                family("F1", parents=["I1"], events=[("E2", True)]),
            ],
            {"I1", "F1"},
        ),
    ],
    ids=["private person", "private name", "private family", "private references"],
)
def test_private_connections_hidden(indexer, rows, guest_finds):
    indexer._add_objects(rows + [event("E1", "birth"), event("E2", "marriage")])
    assert found(indexer, "smith") == {"I1", "F1", "E1", "E2"}
    assert found(indexer, "smith", guest=True) == guest_finds


def test_only_names_expand(indexer):
    """A person's other text does not find their families and events."""
    indexer._add_objects(
        [
            person("I1", "John Smith", text="farmer", events=[("E1", False)]),
            family("F1", parents=["I1"]),
            event("E1", "birth"),
        ]
    )
    assert found(indexer, "farmer") == {"I1"}
    assert found(indexer, "i1") == {"I1"}


def test_redacted_text(indexer):
    indexer._add_objects([person("I1", "John Smith", name_private=True)])
    assert found(indexer, "smith") == {"I1"}
    assert found(indexer, "smith", guest=True) == set()
    assert found(indexer, "i1", guest=True) == {"I1"}


def test_private_object(indexer):
    indexer._add_objects([person("I1", "John Smith", private=True), event("E1", "x")])
    assert indexer.count(include_private=True) == 2
    assert indexer.count(include_private=False) == 1
    assert found(indexer, "i1") == {"I1"}
    assert found(indexer, "i1", guest=True) == set()


def test_update_and_delete(indexer):
    indexer._add_objects(
        [person("I1", "John Smith"), family("F1", parents=["I1"]), event("E1", "x")]
    )
    # renaming the person is the only change needed to find the family by
    # the new name: nothing was copied into the family
    indexer._add_objects([person("I1", "John Miller")])
    assert found(indexer, "smith") == set()
    assert found(indexer, "miller") == {"I1", "F1"}
    # a deleted person's references lead nowhere
    indexer.delete_object("I1", "Person")
    assert found(indexer, "miller") == set()
    assert indexer.count(include_private=True) == 2


def test_direct_matches_rank_first(indexer):
    indexer._add_objects(
        [
            person("I1", "John Smith", events=[("E1", False)]),
            family("F1", parents=["I1"]),
            event("E1", "birth"),
        ]
    )
    _, hits = indexer.search("smith", page=1, pagesize=10)
    assert hits[0]["handle"] == "I1"
    assert [hit["rank"] for hit in hits] == [0, 1, 2]


def test_filters_sort_and_pages(indexer):
    indexer._add_objects(
        [event(f"E{i}", "birth", change=float(i)) for i in range(5)]
        + [person("I1", "Birth Name")]
    )
    assert found(indexer, "birth", object_types=["event"]) == {
        f"E{i}" for i in range(5)
    }
    assert found(indexer, "birth", change_op=">=", change_value=3.0) == {"E3", "E4"}
    _, hits = indexer.search("birth", page=1, pagesize=10, sort=["-change"])
    assert [hit["handle"] for hit in hits][:2] == ["E4", "E3"]
    total, hits = indexer.search("birth", page=2, pagesize=4, sort=["change"])
    assert total == 6 and len(hits) == 2
    total, hits = indexer.search("birth", page=9, pagesize=4)
    assert total == 6 and hits == []
    total, hits = indexer.search("*", page=1, pagesize=2, sort=["change"])
    assert total == 6 and [hit["handle"] for hit in hits] == ["E0", "E1"]


def test_trees_are_separate(indexer):
    other = SearchIndexer(
        tree=f"other-{uuid.uuid4().hex}",
        db_url=indexer.engine.url.render_as_string(hide_password=False),
    )
    try:
        other._add_objects([person("I1", "John Smith")])
        assert found(indexer, "smith") == set()
        assert indexer.count(include_private=True) == 0
        assert found(other, "smith") == {"I1"}
    finally:
        other._delete_all()


def test_chunks(indexer):
    sizes = []
    add_objects = indexer._add_objects

    def record(rows):
        sizes.append(len(rows))
        add_objects(rows)

    indexer._add_objects = record
    indexer._add_objects_chunked(
        (event(f"E{i}", "x") for i in range(25)), chunk_size=10
    )
    assert sizes == [10, 10, 5]
    assert indexer.count(include_private=True) == 25


def test_sifts_tables_dropped(tmp_path):
    """The index of sifts, the former search library, is removed."""
    path = tmp_path / "search.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE documents (id TEXT PRIMARY KEY, name TEXT, metadata JSON,"
        " content TEXT)"
    )
    conn.execute("CREATE VIRTUAL TABLE documents_fts USING fts5(id, content)")
    conn.commit()
    conn.close()
    get_engine(f"sqlite:///{path}")
    conn = sqlite3.connect(path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    conn.close()
    assert "documents" not in tables
    assert "documents_fts" not in tables
    assert "search_doc" in tables


def test_unrelated_documents_table_kept(tmp_path):
    path = tmp_path / "search.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE documents (id TEXT PRIMARY KEY, title TEXT)")
    conn.commit()
    conn.close()
    get_engine(f"sqlite:///{path}")
    conn = sqlite3.connect(path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    conn.close()
    assert "documents" in tables


def _reopen(url: str, tree: str) -> SearchIndexer:
    """An indexer on a new engine, as after restarting the application."""
    schema._engines.pop(url, None)
    return SearchIndexer(tree=tree, db_url=url)


def _version(indexer: SearchIndexer):
    with indexer.engine.connect() as conn:
        return conn.exec_driver_sql("SELECT version FROM search_schema").scalar()


@pytest.mark.parametrize("stored_version", ["same", "other", "none"])
def test_schema_version(tmp_path, stored_version):
    """Tables of another or unknown version are dropped and rebuilt."""
    url = f"sqlite:///{tmp_path}/search.db"
    indexer = _reopen(url, "tree")
    indexer._add_objects([person("I1", "John Smith")])
    indexer._mark_built()
    assert _version(indexer) == schema.SCHEMA_VERSION
    with indexer.engine.connect() as conn:
        if stored_version == "other":
            conn.exec_driver_sql("UPDATE search_schema SET version = 0")
        elif stored_version == "none":
            conn.exec_driver_sql("DROP TABLE search_schema")
        conn.commit()
    indexer = _reopen(url, "tree")
    assert _version(indexer) == schema.SCHEMA_VERSION
    kept = stored_version == "same"
    assert indexer.is_built() is kept
    assert found(indexer, "smith") == ({"I1"} if kept else set())
    # the recreated tables work
    indexer._add_objects([person("I2", "Mary Jones")])
    assert found(indexer, "jones") == {"I2"}
