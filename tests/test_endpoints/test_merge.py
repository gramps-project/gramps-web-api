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

"""Tests for the merge endpoints."""

import os
import unittest
import uuid
from typing import Dict
from unittest.mock import patch

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.auth import add_user, user_db
from gramps_webapi.auth.const import ROLE_EDITOR, ROLE_GUEST, ROLE_OWNER
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG


def get_headers(client, user: str, password: str) -> Dict[str, str]:
    """Return auth headers for the given user."""
    rv = client.post("/api/token/", json={"username": user, "password": password})
    return {"Authorization": f"Bearer {rv.json['access_token']}"}


def make_handle() -> str:
    """Return a fresh unique handle."""
    return str(uuid.uuid4()).replace("-", "")[:20]


class TestMerge(unittest.TestCase):
    """Tests for all merge endpoints using a fresh writable database."""

    @classmethod
    def setUpClass(cls):
        cls.name = "Test Merge API"
        cls.dbman = CLIDbManager(DbState())
        dirpath, _ = cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")
        tree = os.path.basename(dirpath)
        with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
            cls.app = create_app(config_from_env=False)
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        with cls.app.app_context():
            user_db.create_all()
            add_user(name="guest", password="pw", role=ROLE_GUEST, tree=tree)
            add_user(name="editor", password="pw", role=ROLE_EDITOR, tree=tree)
            add_user(name="owner", password="pw", role=ROLE_OWNER, tree=tree)

        cls.headers_guest = get_headers(cls.client, "guest", "pw")
        cls.headers_editor = get_headers(cls.client, "editor", "pw")
        cls.headers_owner = get_headers(cls.client, "owner", "pw")

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _post(self, url, json=None, headers=None):
        return self.client.post(
            url, json=json or {}, headers=headers or self.headers_owner
        )

    def _get(self, url, headers=None):
        return self.client.get(url, headers=headers or self.headers_owner)

    def _merge(self, endpoint, h1, h2, body=None, headers=None):
        return self.client.post(
            f"/api/{endpoint}/{h1}/merge/{h2}",
            json=body or {},
            headers=headers or self.headers_editor,
        )

    def _create_person(self, first_name="Test"):
        handle = make_handle()
        obj = {
            "_class": "Person",
            "handle": handle,
            "gramps_id": f"I{handle[:6]}",
            "gender": 1,
            "primary_name": {
                "_class": "Name",
                "first_name": first_name,
                "surname_list": [{"_class": "Surname", "surname": "Doe"}],
            },
        }
        rv = self._post("/api/people/", json=obj)
        self.assertEqual(rv.status_code, 201, rv.json)
        return handle

    def _create_family(self):
        handle = make_handle()
        obj = {"_class": "Family", "handle": handle, "gramps_id": f"F{handle[:6]}"}
        rv = self._post("/api/families/", json=obj)
        self.assertEqual(rv.status_code, 201, rv.json)
        return handle

    def _create_event(self):
        handle = make_handle()
        obj = {
            "_class": "Event",
            "handle": handle,
            "gramps_id": f"E{handle[:6]}",
            "type": {"_class": "EventType", "string": "Birth"},
        }
        rv = self._post("/api/events/", json=obj)
        self.assertEqual(rv.status_code, 201, rv.json)
        return handle

    def _create_place(self):
        handle = make_handle()
        obj = {
            "_class": "Place",
            "handle": handle,
            "gramps_id": f"P{handle[:6]}",
            "name": {"_class": "PlaceName", "value": "Test Place"},
        }
        rv = self._post("/api/places/", json=obj)
        self.assertEqual(rv.status_code, 201, rv.json)
        return handle

    def _create_source(self):
        handle = make_handle()
        obj = {
            "_class": "Source",
            "handle": handle,
            "gramps_id": f"S{handle[:6]}",
            "title": "Test Source",
        }
        rv = self._post("/api/sources/", json=obj)
        self.assertEqual(rv.status_code, 201, rv.json)
        return handle

    def _create_citation(self, source_handle):
        handle = make_handle()
        obj = {
            "_class": "Citation",
            "handle": handle,
            "gramps_id": f"C{handle[:6]}",
            "source_handle": source_handle,
            "confidence": 2,
        }
        rv = self._post("/api/citations/", json=obj)
        self.assertEqual(rv.status_code, 201, rv.json)
        return handle

    def _create_repository(self):
        handle = make_handle()
        obj = {
            "_class": "Repository",
            "handle": handle,
            "gramps_id": f"R{handle[:6]}",
            "name": "Test Repository",
            "type": {"_class": "RepositoryType", "string": "Library"},
        }
        rv = self._post("/api/repositories/", json=obj)
        self.assertEqual(rv.status_code, 201, rv.json)
        return handle

    def _create_media(self):
        handle = make_handle()
        obj = [
            {
                "_class": "Media",
                "handle": handle,
                "gramps_id": f"O{handle[:6]}",
                "path": "/tmp/test.jpg",
                "mime": "image/jpeg",
                "desc": "Test media",
            }
        ]
        rv = self._post("/api/objects/", json=obj)
        self.assertEqual(rv.status_code, 201, rv.json)
        return handle

    def _create_note(self, text="Test note"):
        handle = make_handle()
        obj = {
            "_class": "Note",
            "handle": handle,
            "gramps_id": f"N{handle[:6]}",
            "text": {"_class": "StyledText", "string": text},
        }
        rv = self._post("/api/notes/", json=obj)
        self.assertEqual(rv.status_code, 201, rv.json)
        return handle

    # ------------------------------------------------------------------
    # Auth / permission checks (tested once via people; apply to all types)
    # ------------------------------------------------------------------

    def test_merge_requires_token(self):
        h1 = self._create_person()
        h2 = self._create_person()
        rv = self.client.post(f"/api/people/{h1}/merge/{h2}", json={})
        self.assertEqual(rv.status_code, 401)

    def test_merge_requires_editor(self):
        h1 = self._create_person()
        h2 = self._create_person()
        rv = self._merge("people", h1, h2, headers=self.headers_guest)
        self.assertEqual(rv.status_code, 403)

    def test_merge_editor_succeeds(self):
        h1 = self._create_person()
        h2 = self._create_person()
        rv = self._merge("people", h1, h2, headers=self.headers_editor)
        self.assertEqual(rv.status_code, 200)

    # ------------------------------------------------------------------
    # Person
    # ------------------------------------------------------------------

    def test_merge_person_phoenix_survives(self):
        h1 = self._create_person(first_name="Survivor")
        h2 = self._create_person(first_name="Gone")
        self.assertEqual(self._merge("people", h1, h2).status_code, 200)
        self.assertEqual(self._get(f"/api/people/{h1}").status_code, 200)
        self.assertEqual(self._get(f"/api/people/{h2}").status_code, 404)

    def test_merge_person_family_merger_param(self):
        h1 = self._create_person()
        h2 = self._create_person()
        rv = self._merge("people", h1, h2, body={"family_merger": False})
        self.assertEqual(rv.status_code, 200)

    def test_merge_person_invalid_family_merger_param(self):
        h1 = self._create_person()
        h2 = self._create_person()
        rv = self._merge("people", h1, h2, body={"family_merger": "notabool"})
        self.assertEqual(rv.status_code, 422)

    def test_merge_person_phoenix_not_found(self):
        h2 = self._create_person()
        rv = self._merge("people", "doesnotexist", h2)
        self.assertEqual(rv.status_code, 404)

    def test_merge_person_titanic_not_found(self):
        h1 = self._create_person()
        rv = self._merge("people", h1, "doesnotexist")
        self.assertEqual(rv.status_code, 404)

    def test_merge_person_spouse_conflict_returns_409(self):
        """Merging two people who are spouses in the same family must return 409."""
        h_father = self._create_person(first_name="Father")
        h_mother = self._create_person(first_name="Mother")
        fam_handle = make_handle()
        fam = {
            "_class": "Family",
            "handle": fam_handle,
            "gramps_id": f"F{fam_handle[:6]}",
            "father_handle": h_father,
            "mother_handle": h_mother,
        }
        self.assertEqual(self._post("/api/families/", json=fam).status_code, 201)
        # update both persons to reference the family
        for handle in (h_father, h_mother):
            rv = self._get(f"/api/people/{handle}")
            data = rv.json
            data["family_list"] = [fam_handle]
            rv2 = self.client.put(
                f"/api/people/{handle}", json=data, headers=self.headers_editor
            )
            self.assertEqual(rv2.status_code, 200)
        rv = self._merge("people", h_father, h_mother)
        self.assertEqual(rv.status_code, 409)

    # ------------------------------------------------------------------
    # Family
    # ------------------------------------------------------------------

    def test_merge_family_phoenix_survives(self):
        h1 = self._create_family()
        h2 = self._create_family()
        self.assertEqual(self._merge("families", h1, h2).status_code, 200)
        self.assertEqual(self._get(f"/api/families/{h1}").status_code, 200)
        self.assertEqual(self._get(f"/api/families/{h2}").status_code, 404)

    def test_merge_family_not_found(self):
        h1 = self._create_family()
        self.assertEqual(self._merge("families", h1, "doesnotexist").status_code, 404)

    def test_merge_family_requires_editor(self):
        h1 = self._create_family()
        h2 = self._create_family()
        rv = self._merge("families", h1, h2, headers=self.headers_guest)
        self.assertEqual(rv.status_code, 403)

    # ------------------------------------------------------------------
    # Event
    # ------------------------------------------------------------------

    def test_merge_event_phoenix_survives(self):
        h1 = self._create_event()
        h2 = self._create_event()
        self.assertEqual(self._merge("events", h1, h2).status_code, 200)
        self.assertEqual(self._get(f"/api/events/{h1}").status_code, 200)
        self.assertEqual(self._get(f"/api/events/{h2}").status_code, 404)

    def test_merge_event_not_found(self):
        h1 = self._create_event()
        self.assertEqual(self._merge("events", h1, "doesnotexist").status_code, 404)

    def test_merge_event_requires_editor(self):
        h1 = self._create_event()
        h2 = self._create_event()
        self.assertEqual(
            self._merge("events", h1, h2, headers=self.headers_guest).status_code, 403
        )

    # ------------------------------------------------------------------
    # Place
    # ------------------------------------------------------------------

    def test_merge_place_phoenix_survives(self):
        h1 = self._create_place()
        h2 = self._create_place()
        self.assertEqual(self._merge("places", h1, h2).status_code, 200)
        self.assertEqual(self._get(f"/api/places/{h1}").status_code, 200)
        self.assertEqual(self._get(f"/api/places/{h2}").status_code, 404)

    def test_merge_place_not_found(self):
        h1 = self._create_place()
        self.assertEqual(self._merge("places", h1, "doesnotexist").status_code, 404)

    # ------------------------------------------------------------------
    # Source
    # ------------------------------------------------------------------

    def test_merge_source_phoenix_survives(self):
        h1 = self._create_source()
        h2 = self._create_source()
        self.assertEqual(self._merge("sources", h1, h2).status_code, 200)
        self.assertEqual(self._get(f"/api/sources/{h1}").status_code, 200)
        self.assertEqual(self._get(f"/api/sources/{h2}").status_code, 404)

    def test_merge_source_not_found(self):
        h1 = self._create_source()
        self.assertEqual(self._merge("sources", h1, "doesnotexist").status_code, 404)

    # ------------------------------------------------------------------
    # Citation
    # ------------------------------------------------------------------

    def test_merge_citation_phoenix_survives(self):
        src = self._create_source()
        h1 = self._create_citation(src)
        h2 = self._create_citation(src)
        self.assertEqual(self._merge("citations", h1, h2).status_code, 200)
        self.assertEqual(self._get(f"/api/citations/{h1}").status_code, 200)
        self.assertEqual(self._get(f"/api/citations/{h2}").status_code, 404)

    def test_merge_citation_not_found(self):
        src = self._create_source()
        h1 = self._create_citation(src)
        self.assertEqual(self._merge("citations", h1, "doesnotexist").status_code, 404)

    def test_merge_citation_requires_editor(self):
        src = self._create_source()
        h1 = self._create_citation(src)
        h2 = self._create_citation(src)
        rv = self._merge("citations", h1, h2, headers=self.headers_guest)
        self.assertEqual(rv.status_code, 403)

    # ------------------------------------------------------------------
    # Repository
    # ------------------------------------------------------------------

    def test_merge_repository_phoenix_survives(self):
        h1 = self._create_repository()
        h2 = self._create_repository()
        self.assertEqual(self._merge("repositories", h1, h2).status_code, 200)
        self.assertEqual(self._get(f"/api/repositories/{h1}").status_code, 200)
        self.assertEqual(self._get(f"/api/repositories/{h2}").status_code, 404)

    def test_merge_repository_not_found(self):
        h1 = self._create_repository()
        self.assertEqual(
            self._merge("repositories", h1, "doesnotexist").status_code, 404
        )

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------

    def test_merge_media_phoenix_survives(self):
        h1 = self._create_media()
        h2 = self._create_media()
        self.assertEqual(self._merge("media", h1, h2).status_code, 200)
        self.assertEqual(self._get(f"/api/media/{h1}").status_code, 200)
        self.assertEqual(self._get(f"/api/media/{h2}").status_code, 404)

    def test_merge_media_not_found(self):
        h1 = self._create_media()
        self.assertEqual(self._merge("media", h1, "doesnotexist").status_code, 404)

    # ------------------------------------------------------------------
    # Note
    # ------------------------------------------------------------------

    def test_merge_note_phoenix_survives(self):
        h1 = self._create_note(text="Keeper")
        h2 = self._create_note(text="Gone")
        self.assertEqual(self._merge("notes", h1, h2).status_code, 200)
        self.assertEqual(self._get(f"/api/notes/{h1}").status_code, 200)
        self.assertEqual(self._get(f"/api/notes/{h2}").status_code, 404)

    def test_merge_note_phoenix_text_preserved(self):
        """After merge the phoenix note's own text is preserved."""
        h1 = self._create_note(text="Phoenix text.")
        h2 = self._create_note(text="Titanic text.")
        self.assertEqual(self._merge("notes", h1, h2).status_code, 200)
        merged_text = self._get(f"/api/notes/{h1}").json["text"]["string"]
        self.assertIn("Phoenix text.", merged_text)

    def test_merge_note_not_found(self):
        h1 = self._create_note()
        self.assertEqual(self._merge("notes", h1, "doesnotexist").status_code, 404)

    def test_merge_note_requires_editor(self):
        h1 = self._create_note()
        h2 = self._create_note()
        rv = self._merge("notes", h1, h2, headers=self.headers_guest)
        self.assertEqual(rv.status_code, 403)
