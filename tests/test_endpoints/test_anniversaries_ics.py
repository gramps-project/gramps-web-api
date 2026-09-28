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

"""Tests for anniversaries ICS endpoint."""

import gzip
import unittest
from unittest.mock import patch
from uuid import uuid4

from gramps_webapi.api.cache import request_cache
from gramps_webapi.auth import (
    add_user,
    get_user_details,
    rotate_user_access_token,
)
from gramps_webapi.auth.const import (
    ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS,
    ROLE_DISABLED,
    ROLE_GUEST,
    ROLE_OWNER,
)

from . import BASE_URL, get_test_client
from .util import fetch_header

ICS_URL = BASE_URL + "/anniversaries.ics"
TOKEN_URL = BASE_URL + "/users/-/access-tokens/anniversaries_ics/"


class TestAnniversariesIcs(unittest.TestCase):
    """Test cases for anniversaries ICS endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def setUp(self):
        """Avoid sharing cached calendars between test cases."""
        with self.client.application.app_context():
            request_cache.clear()

    def _create_token(self, role=ROLE_OWNER):
        """Create or rotate token for role and return (header, token)."""
        header = fetch_header(self.client, role=role)
        rv = self.client.post(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)
        self.assertTrue(rv.json["active"])
        token = rv.json["token"]
        self.assertIsNotNone(token)
        return header, token

    def test_public_feed_requires_valid_token(self):
        """Public feed requires token query parameter and valid token value."""
        rv = self.client.get(ICS_URL)
        self.assertEqual(rv.status_code, 422)

        rv = self.client.get(f"{ICS_URL}?token=invalid-token")
        self.assertEqual(rv.status_code, 401)

    def test_feed_access_and_revoke_flow(self):
        """Public feed works with valid token and fails after revocation."""
        header, token = self._create_token()

        rv = self.client.get(f"{ICS_URL}?token={token}")
        self.assertEqual(rv.status_code, 200)
        self.assertIn("text/calendar", rv.content_type)
        text = rv.data.decode("utf-8")
        self.assertIn("BEGIN:VCALENDAR", text)
        self.assertIn("END:VCALENDAR", text)
        self.assertIn("RRULE:FREQ=YEARLY", text)
        self.assertIn("REFRESH-INTERVAL;VALUE=DURATION:P1D", text)
        self.assertIn("X-PUBLISHED-TTL:P1D", text)
        self.assertEqual(rv.headers["Cache-Control"], "private, max-age=86400")
        self.assertIn("ETag", rv.headers)
        self.assertIn("Last-Modified", rv.headers)
        self.assertIn("Expires", rv.headers)
        etag = rv.headers["ETag"]

        rv = self.client.delete(TOKEN_URL, headers=header)
        self.assertEqual(rv.status_code, 200)

        rv = self.client.get(
            f"{ICS_URL}?token={token}", headers={"If-None-Match": etag}
        )
        self.assertEqual(rv.status_code, 401)

    def test_conditional_feed_does_not_open_database(self):
        """A matching ETag returns 304 after authorization, before DB access."""
        _, token = self._create_token()
        url = f"{ICS_URL}?token={token}&event_types=Birth"
        rv = self.client.get(url)
        self.assertEqual(rv.status_code, 200)

        with patch(
            "gramps_webapi.api.resources.anniversaries.get_db_outside_request"
        ) as get_db:
            conditional = self.client.get(
                url, headers={"If-None-Match": rv.headers["ETag"]}
            )
        self.assertEqual(conditional.status_code, 304)
        self.assertEqual(conditional.data, b"")
        get_db.assert_not_called()

    def test_etag_varies_with_feed_parameters(self):
        """Different representations never share validators."""
        _, token = self._create_token()
        births = self.client.get(f"{ICS_URL}?token={token}&event_types=Birth")
        deaths = self.client.get(f"{ICS_URL}?token={token}&event_types=Death")
        self.assertEqual(births.status_code, 200)
        self.assertEqual(deaths.status_code, 200)
        self.assertNotEqual(births.headers["ETag"], deaths.headers["ETag"])

    def test_feed_without_database_timestamp_uses_body_etag(self):
        """Backends without an early timestamp still receive a body validator."""
        _, token = self._create_token()
        with patch(
            "gramps_webapi.api.resources.anniversaries.get_db_last_change_timestamp",
            return_value=None,
        ):
            rv = self.client.get(f"{ICS_URL}?token={token}&event_types=Marriage")
        self.assertEqual(rv.status_code, 200)
        self.assertIn("ETag", rv.headers)
        self.assertNotIn("Last-Modified", rv.headers)

    def test_calendar_response_supports_gzip(self):
        """Calendar responses use Flask-Compress when requested."""
        _, token = self._create_token()
        rv = self.client.get(
            f"{ICS_URL}?token={token}", headers={"Accept-Encoding": "gzip"}
        )
        self.assertEqual(rv.status_code, 200)
        self.assertEqual(rv.headers["Content-Encoding"], "gzip")
        self.assertIn(b"BEGIN:VCALENDAR", gzip.decompress(rv.data))

    def test_public_feed_event_type_filter(self):
        """event_types filter limits event types included in ICS."""
        _, token = self._create_token(role=ROLE_OWNER)
        rv = self.client.get(f"{ICS_URL}?token={token}&event_types=Birth")
        self.assertEqual(rv.status_code, 200)
        text = rv.data.decode("utf-8")
        self.assertIn("Type: Birth", text)
        self.assertIn("\\nType: Birth", text)
        self.assertNotIn("\\\\nType: Birth", text)
        self.assertNotIn("Type: Death", text)

    def test_public_feed_generation_depth_validation(self):
        """generation_depth is bounded between 1 and 9."""
        _, token = self._create_token(role=ROLE_OWNER)
        rv = self.client.get(f"{ICS_URL}?token={token}&generation_depth=0")
        self.assertEqual(rv.status_code, 422)
        rv = self.client.get(f"{ICS_URL}?token={token}&generation_depth=10")
        self.assertEqual(rv.status_code, 422)

    def test_public_feed_anchor_scope_for_owner_and_guest(self):
        """Anchor scope query works for both owner and guest roles."""
        # Use a known person ID from example_gramps.
        _, owner_token = self._create_token(role=ROLE_OWNER)
        rv = self.client.get(f"{ICS_URL}?token={owner_token}&anchor_gramps_id=I0044")
        self.assertEqual(rv.status_code, 200)

        _, guest_token = self._create_token(role=ROLE_GUEST)
        rv = self.client.get(f"{ICS_URL}?token={guest_token}&anchor_gramps_id=I0044")
        self.assertEqual(rv.status_code, 200)

    def test_public_feed_invalid_anchor(self):
        """Unknown anchor Gramps ID returns 404."""
        _, token = self._create_token(role=ROLE_OWNER)
        rv = self.client.get(
            f"{ICS_URL}?token={token}&anchor_gramps_id=NOT_A_REAL_GRMPS_ID"
        )
        self.assertEqual(rv.status_code, 404)

    def test_public_feed_disabled_user(self):
        """Disabled users cannot use access tokens."""
        username = f"disabled-ics-{uuid4().hex[:8]}"
        with self.client.application.app_context():
            tree = get_user_details("owner")["tree"]
            add_user(
                name=username,
                password="secret",
                role=ROLE_DISABLED,
                tree=tree,
            )
            token = rotate_user_access_token(
                username, ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS
            )
        rv = self.client.get(f"{ICS_URL}?token={token}")
        self.assertEqual(rv.status_code, 403)

    def test_public_feed_disabled_tree(self):
        """If the tree is disabled, feed returns 503."""
        _, token = self._create_token(role=ROLE_OWNER)
        with patch(
            "gramps_webapi.api.resources.anniversaries.is_tree_disabled",
            return_value=True,
        ):
            rv = self.client.get(f"{ICS_URL}?token={token}")
        self.assertEqual(rv.status_code, 503)
