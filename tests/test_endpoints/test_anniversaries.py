#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Gramps Web contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#

"""Tests for the authenticated anniversaries JSON endpoint."""

import json
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import urlencode
from uuid import uuid4

from flask_jwt_extended import create_access_token
from gramps.gen.lib import Date, Event, EventType

from gramps_webapi.api.cache import request_cache
from gramps_webapi.api.resources.anniversaries import (
    AnniversaryEvent,
    _latest_calendar_end,
    _occurrence_dates,
)
from gramps_webapi.auth import add_user, get_guid, get_permissions, get_user_details
from gramps_webapi.auth.const import (
    PERM_VIEW_PRIVATE,
    ROLE_ADMIN,
    ROLE_DISABLED,
    ROLE_GUEST,
    ROLE_OWNER,
)

from . import BASE_URL, get_test_client
from .util import fetch_header

ANNIVERSARIES_URL = BASE_URL + "/anniversaries/"


class TestAnniversaries(unittest.TestCase):
    """Test cases for JSON anniversary occurrences."""

    @classmethod
    def setUpClass(cls):
        """Create the shared test client."""
        cls.client = get_test_client()

    def setUp(self):
        """Avoid sharing cached occurrences between test cases."""
        with self.client.application.app_context():
            request_cache.clear()

    def _get(self, query=None, role=ROLE_OWNER, headers=None, empty_db=False):
        """Request an authenticated anniversary range."""
        auth_header = fetch_header(self.client, role=role, empty_db=empty_db)
        auth_header.update(headers or {})
        query = query or {}
        return self.client.get(
            f"{ANNIVERSARIES_URL}?{urlencode(query)}", headers=auth_header
        )

    def test_requires_jwt_and_date_range(self):
        """The resource requires authentication and both range bounds."""
        rv = self.client.get(f"{ANNIVERSARIES_URL}?start=2026-01-01&end=2026-12-31")
        self.assertEqual(rv.status_code, 401)

        rv = self._get({"start": "2026-01-01"})
        self.assertEqual(rv.status_code, 422)
        rv = self._get({"start": "2026-01-01", "end": "not-a-date"})
        self.assertEqual(rv.status_code, 422)

    def test_rejects_inverted_and_overlong_ranges(self):
        """The date range is ordered and limited to five calendar years."""
        rv = self._get({"start": "2026-02-01", "end": "2026-01-01"})
        self.assertEqual(rv.status_code, 422)

        rv = self._get({"start": "2024-02-29", "end": "2029-03-01"})
        self.assertEqual(rv.status_code, 422)
        self.assertEqual(_latest_calendar_end(date(2024, 2, 29)), date(2029, 2, 28))

        rv = self._get({"start": "2024-02-29", "end": "2029-02-28"})
        self.assertEqual(rv.status_code, 200)

    def test_pagination_parameters_are_bounded(self):
        """Pages are one-based and page sizes have a strict maximum."""
        base = {"start": "2020-01-01", "end": "2021-01-01"}
        for query in (
            {**base, "page": 0},
            {**base, "pagesize": 0},
            {**base, "pagesize": 501},
        ):
            with self.subTest(query=query):
                self.assertEqual(self._get(query).status_code, 422)

    def test_tree_selector_rejects_path_segments(self):
        """An administrator's optional tree selector accepts only tree IDs."""
        rv = self._get(
            {
                "start": "2020-01-01",
                "end": "2021-01-01",
                "tree": "../outside",
            }
        )
        self.assertEqual(rv.status_code, 422)

    def test_occurrences_are_inclusive_and_do_not_precede_historical_event(self):
        """Known-year events begin recurring no earlier than their historical year."""
        self.assertEqual(
            _occurrence_dates(date(1998, 3, 4), date(2001, 3, 4), 2000, 3, 4),
            [date(2000, 3, 4), date(2001, 3, 4)],
        )
        self.assertEqual(
            _occurrence_dates(date(2023, 2, 1), date(2024, 3, 1), 0, 2, 29),
            [date(2023, 2, 28), date(2024, 2, 29)],
        )

    def test_yearless_event_has_null_year_fields_and_localized_event_date(self):
        """Events without a year still recur and expose null age/date fields."""
        event = Event()
        event.handle = "yearless-event"
        event.gramps_id = "E9999"
        event.type = EventType.BIRTH
        event.date = Date(0, 3, 4)
        entry = AnniversaryEvent(
            event,
            (0, 3, 4),
            {("person", "I9999"): "Ada Example"},
        )
        db_handle = Mock()

        with (
            patch(
                "gramps_webapi.api.resources.anniversaries.get_db_manager",
                return_value=SimpleNamespace(name="Example tree"),
            ),
            patch(
                "gramps_webapi.api.resources.anniversaries.get_db_last_change_timestamp",
                return_value=None,
            ),
            patch(
                "gramps_webapi.api.resources.anniversaries.get_db_outside_request",
                return_value=db_handle,
            ),
            patch("gramps_webapi.api.resources.anniversaries.close_db"),
            patch(
                "gramps_webapi.api.resources.anniversaries._collect_anniversaries",
                return_value=[entry],
            ),
        ):
            rv = self._get(
                {
                    "start": "2024-03-04",
                    "end": "2025-03-04",
                    "locale": "en",
                }
            )

        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.headers["X-Total-Count"], "2")
        self.assertEqual(
            [item["occurrence_date"] for item in rv.json],
            ["2024-03-04", "2025-03-04"],
        )
        self.assertTrue(all(item["anniversary"] is None for item in rv.json))
        self.assertTrue(all(item["historical_date"] is None for item in rv.json))
        self.assertTrue(all(item["event_date"] for item in rv.json))
        self.assertEqual(
            rv.json[0]["event"],
            {"handle": "yearless-event", "gramps_id": "E9999"},
        )
        self.assertEqual(
            rv.json[0]["participants"],
            [
                {
                    "object_type": "person",
                    "gramps_id": "I9999",
                    "name": "Ada Example",
                }
            ],
        )

    def test_pagination_uses_shared_occurrence_cache_and_distinct_etags(self):
        """The full range is cached once while each page has its own ETag."""
        query = {
            "start": "2020-01-01",
            "end": "2021-01-01",
            "event_types": "all",
            "living_only": "false",
            "pagesize": 1,
            "locale": "en",
        }
        first = self._get({**query, "page": 1})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.content_type, "application/json")
        self.assertEqual(first.headers["Cache-Control"], "private, max-age=86400")
        self.assertIn("Expires", first.headers)
        self.assertNotIn("Last-Modified", first.headers)
        self.assertEqual(len(first.json), 1)
        total = int(first.headers["X-Total-Count"])
        self.assertGreater(total, 1)

        with patch(
            "gramps_webapi.api.resources.anniversaries.get_db_outside_request"
        ) as get_db:
            second = self._get({**query, "page": 2})
        get_db.assert_not_called()

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.headers["X-Total-Count"], str(total))
        self.assertNotEqual(first.headers["ETag"], second.headers["ETag"])
        self.assertNotEqual(first.json[0], second.json[0])

        beyond = self._get({**query, "page": total + 1})
        self.assertEqual(beyond.status_code, 200)
        self.assertEqual(beyond.json, [])
        self.assertEqual(beyond.headers["X-Total-Count"], str(total))

    def test_tree_scope_isolation_and_multi_tree_admin_access(self):
        """Tree-bound users stay scoped while admins can use an authorized tree."""
        query = {
            "start": "2020-01-01",
            "end": "2021-01-01",
            "living_only": "false",
        }
        owner = self._get(query, role=ROLE_OWNER)
        other_tree = self._get(query, role=ROLE_OWNER, empty_db=True)
        self.assertEqual(owner.status_code, 200)
        self.assertEqual(other_tree.status_code, 200)
        self.assertEqual(other_tree.headers["X-Total-Count"], "0")
        self.assertNotEqual(owner.headers["ETag"], other_tree.headers["ETag"])

        with self.client.application.app_context():
            admin_name = f"calendar-admin-{uuid4().hex[:8]}"
            add_user(
                name=admin_name,
                password="secret",
                role=ROLE_ADMIN,
                tree=None,
            )
            tree_id = get_user_details("owner_empty")["tree"]
            permissions = get_permissions(admin_name, tree_id)
            admin_token = create_access_token(
                identity=get_guid(admin_name),
                additional_claims={"permissions": list(permissions)},
            )
            owner_id = get_guid("owner")
            owner_permissions = get_permissions("owner", tree_id)
            owner_tree = get_user_details("owner")["tree"]
            mismatched_owner_token = create_access_token(
                identity=owner_id,
                additional_claims={
                    "tree": owner_tree,
                    "permissions": list(owner_permissions),
                },
            )

        other_tree_query = {**query, "tree": tree_id}
        admin_response = self.client.get(
            f"{ANNIVERSARIES_URL}?{urlencode(other_tree_query)}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response.headers["X-Total-Count"], "0")

        unauthorized_response = self.client.get(
            f"{ANNIVERSARIES_URL}?{urlencode(other_tree_query)}",
            headers={"Authorization": f"Bearer {mismatched_owner_token}"},
        )
        self.assertEqual(unauthorized_response.status_code, 403)

    def test_matching_etag_returns_304_before_opening_database(self):
        """An authorized matching validator returns before database access."""
        query = {
            "start": "2020-01-01",
            "end": "2021-01-01",
            "living_only": "false",
        }
        first = self._get(query)
        self.assertEqual(first.status_code, 200)

        with patch(
            "gramps_webapi.api.resources.anniversaries.get_db_outside_request"
        ) as get_db:
            conditional = self._get(
                query, headers={"If-None-Match": first.headers["ETag"]}
            )
        self.assertEqual(conditional.status_code, 304)
        get_db.assert_not_called()

    def test_fallback_without_database_timestamp_skips_server_cache(self):
        """A missing tree timestamp uses a generated validator without caching."""
        query = {
            "start": "2020-01-01",
            "end": "2021-01-01",
            "living_only": "false",
        }
        with (
            patch(
                "gramps_webapi.api.resources.anniversaries.get_db_last_change_timestamp",
                return_value=None,
            ),
            patch(
                "gramps_webapi.api.resources.anniversaries.request_cache.set"
            ) as cache_set,
        ):
            rv = self._get(query)
        self.assertEqual(rv.status_code, 200)
        self.assertIn("ETag", rv.headers)
        cache_set.assert_not_called()

    def test_private_permission_uses_current_role_and_jwt_claims(self):
        """Different effective privacy access produces separate representations."""
        query = {
            "start": "2020-01-01",
            "end": "2021-01-01",
            "living_only": "false",
        }
        owner = self._get(query, role=ROLE_OWNER)
        guest = self._get(query, role=ROLE_GUEST)
        self.assertEqual(owner.status_code, 200)
        self.assertEqual(guest.status_code, 200)
        self.assertNotEqual(owner.headers["ETag"], guest.headers["ETag"])

        with self.client.application.app_context():
            tree_id = get_user_details("owner")["tree"]
            permissions = get_permissions("owner", tree_id)
            permissions.discard(PERM_VIEW_PRIVATE)
            token = create_access_token(
                identity=get_guid("owner"),
                additional_claims={
                    "tree": tree_id,
                    "permissions": list(permissions),
                },
            )
        owner_without_private_claim = self.client.get(
            f"{ANNIVERSARIES_URL}?{urlencode(query)}",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(owner_without_private_claim.status_code, 200)
        self.assertEqual(
            owner_without_private_claim.headers["ETag"], guest.headers["ETag"]
        )

    def test_disabled_account_and_tree_are_rejected(self):
        """A stale JWT cannot keep access after account or tree disablement."""
        with self.client.application.app_context():
            tree = get_user_details("owner")["tree"]
            username = f"disabled-anniversaries-{uuid4().hex[:8]}"
            add_user(
                name=username,
                password="secret",
                role=ROLE_DISABLED,
                tree=tree,
            )
            token = create_access_token(
                identity=get_guid(username),
                additional_claims={"tree": tree, "permissions": []},
            )
        disabled = self.client.get(
            f"{ANNIVERSARIES_URL}?start=2020-01-01&end=2021-01-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(disabled.status_code, 403)

        query = {"start": "2020-01-01", "end": "2021-01-01"}
        with patch(
            "gramps_webapi.api.resources.anniversaries.is_tree_disabled",
            return_value=True,
        ):
            tree_disabled = self._get(query)
        self.assertEqual(tree_disabled.status_code, 503)

    def test_native_event_rules_intersect_with_event_types(self):
        """The JSON endpoint delegates event and person filtering to Gramps."""
        rv = self._get(
            {
                "start": "2020-01-01",
                "end": "2021-01-01",
                "event_types": "Birth",
                "living_only": "false",
                "rules": json.dumps(
                    {"rules": [{"name": "HasType", "values": ["Death"]}]}
                ),
            }
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json, [])
        self.assertEqual(rv.headers["X-Total-Count"], "0")

    def test_all_event_types_still_intersect_with_native_rules(self):
        """The all selector and a named type share the same Gramps filter logic."""
        common = {
            "start": "2020-01-01",
            "end": "2021-01-01",
            "living_only": "false",
            "rules": json.dumps({"rules": [{"name": "HasType", "values": ["Death"]}]}),
        }
        named = self._get({**common, "event_types": "Death"})
        all_types = self._get({**common, "event_types": "ALL"})
        self.assertEqual(named.status_code, 200)
        self.assertEqual(all_types.status_code, 200)
        self.assertEqual(named.json, all_types.json)
        self.assertEqual(
            named.headers["X-Total-Count"], all_types.headers["X-Total-Count"]
        )
        self.assertGreater(int(named.headers["X-Total-Count"]), 0)

    def test_openapi_documents_json_response_and_pagination(self):
        """The occurrence schema and query parameters are discoverable."""
        rv = self.client.get(f"{BASE_URL}/openapi.json")
        self.assertEqual(rv.status_code, 200)
        specification = rv.json
        path = specification["paths"][f"{BASE_URL}/anniversaries/"]["get"]
        parameters = {parameter["name"] for parameter in path["parameters"]}
        self.assertTrue({"start", "end", "page", "pagesize", "tree"} <= parameters)
        self.assertIn("X-Total-Count", path["responses"]["200"]["headers"])
        documented = json.dumps(specification)
        for field in (
            "occurrence_date",
            "historical_date",
            "anniversary",
            "event_date",
            "participants",
            "object_type",
        ):
            self.assertIn(field, documented)


if __name__ == "__main__":
    unittest.main()
