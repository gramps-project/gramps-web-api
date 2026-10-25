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

"""References to objects that are missing must not break anything.

Objects can be missing from a damaged tree. `RestrictedDb` also removes
references to objects it hides, so these must work through it, too.
"""

import pytest
from gramps.gen.db import DbTxn
from gramps.gen.db.utils import make_database
from gramps.gen.lib import EventRef, Family, Person, PersonRef

from gramps_webapi.api.access import AccessPolicy, RestrictedDb
from gramps_webapi.api.resources.dna import get_match_data
from gramps_webapi.api.resources.sort import Sort
from gramps_webapi.api.resources.timeline import Timeline
from gramps_webapi.verify_lib import run_verify


@pytest.fixture(scope="module")
def db():
    """A tree with a person and a family referencing missing objects."""
    database = make_database("sqlite")
    database.load(":memory:")
    with DbTxn("add", database) as trans:
        person = Person()
        ref = EventRef()
        ref.set_reference_handle("missingevent")
        person.add_event_ref(ref)
        person.add_family_handle("missingfamily")
        association = PersonRef()
        association.set_reference_handle("missingperson")
        association.set_relation("DNA")
        person.add_person_ref(association)
        database.add_person(person, trans)
        family = Family()
        family.set_father_handle("missingperson")
        family.set_mother_handle(person.handle)
        database.add_family(family, trans)
        person.add_family_handle(family.handle)
        database.commit_person(person, trans)
    yield database, person.handle, family.handle
    database.close()


@pytest.fixture(params=["base", "restricted"])
def view(db, request):
    """The tree as seen through the base and a restricted database.

    Not through Gramps' private proxy, which itself fails on missing
    references.
    """
    database, person_handle, family_handle = db
    if request.param == "restricted":
        database = RestrictedDb(database, AccessPolicy(view_private=False))
    return database, person_handle, family_handle


def test_timeline(view):
    database, person_handle, family_handle = view
    timeline = Timeline(database)
    timeline.add_person(person_handle)
    timeline.add_family(family_handle)


def test_family_sort_keys(view):
    database, _, family_handle = view
    family = database.get_family_from_handle(family_handle)
    sort = Sort(database)
    sort.by_family_surname_key(family)
    sort.by_family_soundex_key(family)


def test_dna_match_with_missing_person(view):
    database, person_handle, _ = view
    person = database.get_person_from_handle(person_handle)
    for index, association in enumerate(person.get_person_ref_list()):
        assert get_match_data(database, person, index) is None


def test_verify(db):
    database, _, _ = db
    run_verify(database)
