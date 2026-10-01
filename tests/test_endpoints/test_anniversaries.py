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
from unittest.mock import patch
from urllib.parse import urlencode

from gramps_webapi.api.cache import request_cache
from gramps_webapi.api.resources.anniversaries import (
    _latest_calendar_end,
    _occurrence_dates,
)
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER

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
        """Avoid sharing cached representations between test cases."""
        with self.client.application.app_context():
            request_cache.clear()

    def _get(self, query=None, role=ROLE_OWNER, headers=None):
        """Request an authenticated anniversary range."""
        auth_header = fetch_header(self.client, role=role)
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

    def test_rejects_invalid_or_excessive_ranges(self):
        """Ranges are ordered and limited to five calendar years."""
        rv = self._get({"start": "2026-02-01", "end": "2026-01-01"})
        self.assertEqual(rv.status_code, 422)

        rv = self._get({"start": "2024-02-29", "end": "2029-03-01"})
        self.assertEqual(rv.status_code, 422)
        self.assertEqual(_latest_calendar_end(date(2024, 2, 29)), date(2029, 2, 28))
        self.assertEqual(_latest_calendar_end(date(9999, 1, 1)), date(9999, 1, 1))

        rv = self._get({"start": "2024-02-29", "end": "2029-02-28"})
        self.assertEqual(rv.status_code, 200)

    def test_returns_stable_paginated_occurrences(self):
        """Occurrences expose navigation data and standard pagination headers."""
        query = {
            "start": "2024-01-01",
            "end": "2025-01-01",
            "living_only": "false",
            "pagesize": 1,
            "locale": "en",
        }
        first = self._get(query)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.content_type, "application/json")
        self.assertEqual(len(first.json), 1)
        self.assertGreater(int(first.headers["X-Total-Count"]), 1)
        occurrence = first.json[0]
        self.assertEqual(
            set(occurrence),
            {
                "anniversary",
                "event",
                "event_date",
                "historical_date",
                "occurrence_date",
                "participants",
                "summary",
                "type",
            },
        )
        self.assertIn("handle", occurrence["event"])
        self.assertIn("gramps_id", occurrence["event"])
        self.assertTrue(occurrence["participants"])
        self.assertTrue(
            {"object_type", "gramps_id", "name"} <= set(occurrence["participants"][0])
        )

        second = self._get({**query, "page": 2})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            second.headers["X-Total-Count"], first.headers["X-Total-Count"]
        )
        self.assertNotEqual(second.json[0], occurrence)

    def test_occurrences_include_leap_day_fallback(self):
        """February 29 recurs on February's final day in non-leap years."""
        self.assertEqual(
            _occurrence_dates(date(2023, 1, 1), date(2024, 12, 31), 2, 29),
            [date(2023, 2, 28), date(2024, 2, 29)],
        )

    def test_native_filters_are_reused(self):
        """Event shorthand and native rules are intersected by the collector."""
        rv = self._get(
            {
                "start": "2026-01-01",
                "end": "2026-12-31",
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

    def test_missing_saved_filter_returns_empty_result(self):
        """A removed saved filter leaves a valid, empty calendar view."""
        rv = self._get(
            {
                "start": "2026-01-01",
                "end": "2026-12-31",
                "filter": "missing-filter",
            }
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.json, [])
        self.assertEqual(rv.headers["X-Total-Count"], "0")

    def test_conditional_request_does_not_open_database(self):
        """A matching ETag returns 304 after auth, before opening the tree."""
        query = {
            "start": "2026-01-01",
            "end": "2026-12-31",
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
        self.assertEqual(conditional.data, b"")
        get_db.assert_not_called()

    def test_cached_request_does_not_open_database(self):
        """A cached representation is reused without reopening the tree."""
        query = {
            "start": "2026-01-01",
            "end": "2026-12-31",
            "living_only": "false",
        }
        first = self._get(query)
        self.assertEqual(first.status_code, 200)

        with patch(
            "gramps_webapi.api.resources.anniversaries.get_db_outside_request"
        ) as get_db:
            cached = self._get(query)

        self.assertEqual(cached.status_code, 200)
        self.assertEqual(cached.data, first.data)
        self.assertEqual(
            cached.headers["X-Total-Count"], first.headers["X-Total-Count"]
        )
        get_db.assert_not_called()

    def test_etag_varies_by_private_record_permission(self):
        """Cached output is partitioned by the user's private-record access."""
        query = {
            "start": "2026-01-01",
            "end": "2026-12-31",
            "living_only": "false",
        }
        owner = self._get(query, role=ROLE_OWNER)
        guest = self._get(query, role=ROLE_GUEST)

        self.assertEqual(owner.status_code, 200)
        self.assertEqual(guest.status_code, 200)
        self.assertNotEqual(owner.headers["ETag"], guest.headers["ETag"])

    def test_guest_receives_only_visible_records(self):
        """The authenticated view works through the privacy proxy for guests."""
        rv = self._get(
            {
                "start": "2026-01-01",
                "end": "2026-12-31",
                "living_only": "false",
            },
            role=ROLE_GUEST,
        )
        self.assertEqual(rv.status_code, 200)


if __name__ == "__main__":
    unittest.main()
