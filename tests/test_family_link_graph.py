#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026       Doug Blank
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

"""Tests for family link graphs read on demand through a RestrictedDb."""

import random

import pytest
from gramps.gen.db.utils import open_database
from gramps.gen.lib import ChildRefType
from gramps.gen.relationship import get_relationship_calculator

from gramps_webapi.api.access import AccessPolicy, RestrictedDb
from gramps_webapi.future_gramps.relationship_path import (
    FamilyLinkGraph,
    find_connections,
    label_path,
)
from tests import ExampleDbSQLite
from tests.test_privacy_canary import _plant

TREE_NAME = "example_family_link_graph"


@pytest.fixture(scope="module")
def db():
    """The example tree, with private canaries."""
    ExampleDbSQLite(name=TREE_NAME)
    database = open_database(TREE_NAME, force_unlock=True)
    _plant(database)
    yield database
    database.close()


def _full_graph(db) -> FamilyLinkGraph:
    """A graph of all people and families the database returns."""
    graph = FamilyLinkGraph()
    for person in db.iter_people():
        graph.add_person(person.handle, person.get_gender())
    for family in db.iter_families():
        graph.add_family(
            family.handle,
            family.get_father_handle(),
            family.get_mother_handle(),
            [
                (
                    ref.ref,
                    ref.get_mother_relation() == ChildRefType.BIRTH,
                    ref.get_father_relation() == ChildRefType.BIRTH,
                )
                for ref in family.get_child_ref_list()
            ],
        )
    return graph


def _pairs(graph: FamilyLinkGraph) -> list[tuple[str, str]]:
    """Pairs of people a few links apart, and some random pairs."""
    rng = random.Random(1)
    people = sorted(graph._gender)
    pairs = []
    while len(pairs) < 25:
        start = rng.choice(people)
        near = sorted(h for h, d in graph.distances(start, 8).items() if d >= 2)
        if near:
            pairs.append((start, rng.choice(near)))
    pairs += [tuple(rng.sample(people, 2)) for _ in range(10)]
    return pairs


@pytest.mark.parametrize("restricted", [False, True])
@pytest.mark.parametrize("blood_only", [False, True])
def test_same_as_full_graph(db, restricted, blood_only):
    """A graph read on demand finds and labels the same paths."""
    database = RestrictedDb(db, AccessPolicy(view_private=False)) if restricted else db
    full = _full_graph(database)
    calc = get_relationship_calculator()
    found = 0
    for start, end in _pairs(full):
        graph = FamilyLinkGraph.from_db(database)
        kwargs = {"max_depth": 10, "max_results": 5, "blood_only": blood_only}
        expected = find_connections(full, start, end, **kwargs)
        paths = find_connections(graph, start, end, **kwargs)
        assert paths == expected
        assert [label_path(calc, database, graph, p) for p in paths] == [
            label_path(calc, database, full, p) for p in expected
        ]
        # only part of the tree is read
        assert len(graph) < len(full)
        found += bool(paths)
    # pairs are chosen by any links, so fewer are blood relatives
    assert found >= (3 if blood_only else 10)


def test_hidden_people_are_not_read(db):
    """A RestrictedDb never gives the graph a hidden person."""
    restricted = RestrictedDb(db, AccessPolicy(view_private=False))
    visible = set(_full_graph(restricted)._gender)
    hidden = set(_full_graph(db)._gender) - visible
    assert hidden
    graph = FamilyLinkGraph.from_db(restricted)
    for handle in sorted(hidden)[:20]:
        assert handle not in graph
    for handle in sorted(visible)[:200]:
        graph.distances(handle, 3)
    assert not set(graph._gender) & hidden
