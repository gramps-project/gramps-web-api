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

"""Edits through the API are reflected in search, including privacy."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from gramps_webapi.api.search import get_search_indexer
from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_EXAMPLE_GRAMPS_AUTH_CONFIG
from gramps_webapi.dbmanager import WebDbManager
from tests import ExampleDbSQLite

TREE_NAME = "search_updates"
USERS = {
    ROLE_OWNER: ("search_owner", "owner-pw"),
    ROLE_GUEST: ("search_guest", "guest-pw"),
}
PERSON, EVENT, FAMILY = "zqupdP1", "zqupdE1", "zqupdF1"


@pytest.fixture(scope="module")
def api():
    """A client for a tree whose search index is built, and auth headers."""
    ExampleDbSQLite(name=TREE_NAME)
    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_EXAMPLE_GRAMPS_AUTH_CONFIG}):
        app = create_app(
            config={"TESTING": True, "RATELIMIT_ENABLED": False},
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
    headers = {}
    for role, (name, password) in USERS.items():
        rv = client.post("/api/token/", json={"username": name, "password": password})
        headers[role] = {"Authorization": f"Bearer {rv.json['access_token']}"}
    return client, headers[ROLE_OWNER], headers[ROLE_GUEST]


def test_edits_update_search(api):
    client, owner, guest = api

    def search(query: str, headers) -> set[str]:
        rv = client.get(f"/api/search/?query={query}", headers=headers)
        assert rv.status_code == 200, rv.json
        return {hit["handle"] for hit in rv.json}

    def edit_person(**changes) -> None:
        person = client.get(f"/api/people/{PERSON}", headers=owner).json
        for key, value in changes.items():
            if key == "first_name":
                person["primary_name"]["first_name"] = value
            elif key == "ref_private":
                person["event_ref_list"][0]["private"] = value
            else:
                person[key] = value
        rv = client.put(f"/api/people/{PERSON}", json=person, headers=owner)
        assert rv.status_code == 200, rv.json

    objects = [
        {
            "_class": "Person",
            "handle": PERSON,
            "primary_name": {
                "_class": "Name",
                "first_name": "Zqupdated",
                "surname_list": [{"_class": "Surname", "surname": "Canary"}],
            },
            "event_ref_list": [
                {
                    "_class": "EventRef",
                    "ref": EVENT,
                    "role": {"_class": "EventRoleType", "string": "Primary"},
                }
            ],
        },
        {
            "_class": "Event",
            "handle": EVENT,
            "type": {"_class": "EventType", "string": "Birth"},
        },
        {"_class": "Family", "handle": FAMILY, "father_handle": PERSON},
    ]
    rv = client.post("/api/objects/", json=objects, headers=owner)
    assert rv.status_code == 201, rv.json
    everything = {PERSON, EVENT, FAMILY}
    assert search("zqupdated", guest) == everything

    edit_person(private=True)
    assert search("zqupdated", guest) == set()
    assert search("zqupdated", owner) == everything

    # the family and event are found by the new name, the old one is gone
    edit_person(private=False, first_name="Zqrenamed")
    assert search("zqupdated", owner) == set()
    assert search("zqrenamed", guest) == everything

    edit_person(ref_private=True)
    assert search("zqrenamed", guest) == {PERSON, FAMILY}
    assert search("zqrenamed", owner) == everything

    rv = client.delete(f"/api/people/{PERSON}", headers=owner)
    assert rv.status_code == 200, rv.json
    assert search("zqrenamed", owner) == set()
