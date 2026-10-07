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
import json
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode
from uuid import uuid4

from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.lib import (
    Date,
    Event,
    EventRef,
    EventRoleType,
    EventType,
    Family,
    Person,
)

from gramps_webapi.api.cache import request_cache
from gramps_webapi.api.resources.anniversaries import (
    AnniversaryEvent,
    _build_ics,
    _collect_anniversaries,
    _escape_ics_text,
    _get_anniversary_date_components,
)
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

    def test_calendar_serialization_is_utf8_safe(self):
        """Long Unicode text is folded without splitting encoded characters."""
        event = Event()
        event.handle = "event-handle"
        event.gramps_id = "E0001"
        event.type = EventType(EventType.BIRTH)
        event.date = Date(2000, 1, 2)
        event.change = 1_700_000_000
        entry = AnniversaryEvent(event, {("person", "I0001"): "Éléonore, " * 20})
        payload = _build_ics([entry], "tree", "My family tree", GRAMPS_LOCALE)
        lines = payload.removesuffix("\r\n").split("\r\n")
        self.assertTrue(all(len(line.encode("utf-8")) <= 75 for line in lines))
        self.assertTrue(any(line.startswith(" ") for line in lines))
        self.assertIn("X-WR-CALNAME:My family tree - ", payload)

    def test_february_29_repeats_on_last_day_of_february(self):
        """Leap-day anniversaries recur every year on February's last day."""
        event = Event()
        event.handle = "leap-event"
        event.gramps_id = "E0002"
        event.type = EventType(EventType.BIRTH)
        event.date = Date(2000, 2, 29)
        payload = _build_ics([AnniversaryEvent(event)], "tree", "Tree")
        self.assertIn("RRULE:FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=-1", payload)
        self.assertIn("DTSTART;VALUE=DATE:20000229", payload)

    def test_ics_text_escaping_normalizes_all_line_endings(self):
        """CR, LF, commas, semicolons and slashes are escaped once."""
        escaped = _escape_ics_text("one\r\ntwo\rthree\nfour, five; \\six")
        self.assertEqual(escaped, "one\\ntwo\\nthree\\nfour\\, five\\; \\\\six")

    def test_only_exact_dates_are_anniversaries(self):
        """Estimated, calculated and approximate dates are excluded."""
        event = Event()
        event.date = Date(2000, 3, 4)
        self.assertEqual(_get_anniversary_date_components(event), (2000, 3, 4))
        event.date.set_modifier(Date.MOD_ABOUT)
        self.assertIsNone(_get_anniversary_date_components(event))

    def test_public_feed_event_type_filter(self):
        """event_types filter limits event types included in ICS."""
        _, token = self._create_token(role=ROLE_OWNER)
        rv = self.client.get(f"{ICS_URL}?token={token}&event_types=Birth&locale=en")
        self.assertEqual(rv.status_code, 200)
        text = rv.data.decode("utf-8")
        self.assertIn("Type: Birth", text)
        self.assertIn("\\nType: Birth", text)
        self.assertNotIn("\\\\nType: Birth", text)
        self.assertNotIn("Type: Death", text)

    def test_event_types_match_case_and_requested_locale_with_shared_cache_key(self):
        """Case variants share content and translated names select the same events."""
        header, token = self._create_token()
        self.addCleanup(self.client.delete, TOKEN_URL, headers=header)
        for first, second in (("birth", "Birth"), ("Birth", "birth")):
            with self.subTest(first=first):
                with self.client.application.app_context():
                    request_cache.clear()
                responses = [
                    self.client.get(
                        f"{ICS_URL}?{urlencode({'token': token, 'event_types': value, 'locale': 'en'})}"
                    )
                    for value in (first, second)
                ]
                self.assertTrue(all(rv.status_code == 200 for rv in responses))
                self.assertIn(b"BEGIN:VEVENT", responses[0].data)
                self.assertEqual(responses[0].data, responses[1].data)
                self.assertEqual(
                    responses[0].headers["ETag"], responses[1].headers["ETag"]
                )

        german_locale = Mock(wraps=GRAMPS_LOCALE)
        german_locale.language = ["de"]
        german_locale.translation = Mock(wraps=GRAMPS_LOCALE.translation)
        german_locale.translation.sgettext.side_effect = lambda value: (
            "Geburt" if value == "Birth" else GRAMPS_LOCALE.translation.sgettext(value)
        )
        with patch(
            "gramps_webapi.api.resources.anniversaries.get_locale_for_language",
            return_value=german_locale,
        ):
            german = [
                self.client.get(
                    f"{ICS_URL}?{urlencode({'token': token, 'event_types': value, 'locale': 'de'})}"
                )
                for value in ("Birth", "Geburt", "geburt")
            ]
        self.assertTrue(all(rv.status_code == 200 for rv in german))
        self.assertIn(b"BEGIN:VEVENT", german[0].data)
        self.assertEqual(german[0].data, german[1].data)
        self.assertEqual(german[1].data, german[2].data)
        self.assertEqual(german[1].headers["ETag"], german[2].headers["ETag"])

    def _collect_with_options(self, living_only, primary_participants_only):
        """Collect deterministic person and family references with real Gramps roles."""
        people = {}
        for handle in ("alive", "partner", "deceased"):
            person = Person()
            person.handle = handle
            person.gramps_id = handle
            people[handle] = person

        events = {}

        def add_event(subject, handle, event_type, role=EventRoleType.PRIMARY):
            event = Event()
            event.handle = handle
            event.gramps_id = handle
            event.type = EventType(event_type)
            event.date = Date(2000, 1, 2)
            events[handle] = event
            reference = EventRef()
            reference.set_reference_handle(handle)
            reference.set_role(role)
            subject.add_event_ref(reference)

        add_event(people["alive"], "alive-birth", EventType.BIRTH)
        add_event(people["deceased"], "deceased-birth", EventType.BIRTH)
        add_event(people["deceased"], "deceased-death", EventType.DEATH)
        add_event(
            people["alive"], "witness-birth", EventType.BIRTH, EventRoleType.WITNESS
        )

        families = {}
        for handle, spouse in (
            ("living-family", "partner"),
            ("mixed-family", "deceased"),
        ):
            family = Family()
            family.handle = handle
            family.gramps_id = handle
            family.set_father_handle("alive")
            family.set_mother_handle(spouse)
            people["alive"].add_family_handle(handle)
            people[spouse].add_family_handle(handle)
            families[handle] = family
            add_event(
                family, handle + "-marriage", EventType.MARRIAGE, EventRoleType.FAMILY
            )
        add_event(
            families["living-family"],
            "witness-marriage",
            EventType.MARRIAGE,
            EventRoleType.WITNESS,
        )

        db_handle = Mock()
        db_handle.get_person_handles.return_value = list(people)
        db_handle.get_person_from_handle.side_effect = people.get
        db_handle.get_family_from_handle.side_effect = families.get
        db_handle.get_event_from_handle.side_effect = events.get
        args = {
            "event_types": ["Birth", "Marriage", "Death"],
            "living_only": living_only,
            "primary_participants_only": primary_participants_only,
        }
        with (
            patch(
                "gramps_webapi.api.resources.anniversaries.CacheProxyDb",
                side_effect=lambda db: db,
            ),
            patch(
                "gramps_webapi.api.resources.anniversaries.probably_alive",
                side_effect=lambda person, db, today: person.handle != "deceased",
            ),
            patch(
                "gramps_webapi.api.resources.anniversaries.get_family_name_localized",
                return_value="Family",
            ),
        ):
            return {
                entry.event.handle
                for entry in _collect_anniversaries(db_handle, args, GRAMPS_LOCALE)
            }

    def test_living_only_filters_births_and_marriages_but_keeps_deaths(self):
        """Dead people's births and mixed-family marriages are optional."""
        living = self._collect_with_options(True, True)
        all_people = self._collect_with_options(False, True)
        self.assertEqual(
            living,
            {"alive-birth", "deceased-death", "living-family-marriage"},
        )
        self.assertEqual(
            all_people,
            living | {"deceased-birth", "mixed-family-marriage"},
        )

    def test_primary_participants_only_excludes_secondary_roles(self):
        """Witness references appear only when secondary participants are allowed."""
        primary = self._collect_with_options(False, True)
        secondary = self._collect_with_options(False, False)
        self.assertEqual(
            secondary,
            primary | {"witness-birth", "witness-marriage"},
        )

    def test_public_feed_generation_depth_validation(self):
        """generation_depth is bounded between 1 and 9."""
        _, token = self._create_token(role=ROLE_OWNER)
        rv = self.client.get(f"{ICS_URL}?token={token}&generation_depth=0")
        self.assertEqual(rv.status_code, 422)
        rv = self.client.get(f"{ICS_URL}?token={token}&generation_depth=10")
        self.assertEqual(rv.status_code, 422)

    def test_native_event_rules_intersect_with_event_types(self):
        """Public shorthand and native Event rules are intersected."""
        _, token = self._create_token()
        query = urlencode(
            {
                "token": token,
                "event_types": "Birth",
                "living_only": "false",
                "locale": "en",
                "rules": json.dumps(
                    {"rules": [{"name": "HasType", "values": ["Death"]}]}
                ),
            }
        )
        rv = self.client.get(f"{ICS_URL}?{query}")
        self.assertEqual(rv.status_code, 200)
        self.assertNotIn("BEGIN:VEVENT", rv.data.decode("utf-8"))

    def test_native_person_rules_limit_collected_events(self):
        """Native Person rules are applied before event collection."""
        _, token = self._create_token()
        common = {
            "token": token,
            "event_types": "Birth",
            "living_only": "false",
            "locale": "en",
        }
        all_births = self.client.get(f"{ICS_URL}?{urlencode(common)}")
        person_query = {
            **common,
            "person_rules": json.dumps(
                {"rules": [{"name": "HasIdOf", "values": ["I0044"]}]}
            ),
        }
        selected = self.client.get(f"{ICS_URL}?{urlencode(person_query)}")
        self.assertEqual(selected.status_code, 200)
        self.assertGreater(selected.data.count(b"BEGIN:VEVENT"), 0)
        self.assertLess(
            selected.data.count(b"BEGIN:VEVENT"),
            all_births.data.count(b"BEGIN:VEVENT"),
        )

    def test_missing_saved_filter_returns_empty_calendar(self):
        """A deleted saved filter does not permanently break a subscription."""
        _, token = self._create_token()
        rv = self.client.get(
            f"{ICS_URL}?{urlencode({'token': token, 'filter': 'missing-filter'})}"
        )
        self.assertEqual(rv.status_code, 200)
        self.assertNotIn(b"BEGIN:VEVENT", rv.data)

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
        """Unknown anchor Gramps ID returns a valid empty calendar."""
        _, token = self._create_token(role=ROLE_OWNER)
        rv = self.client.get(
            f"{ICS_URL}?token={token}&anchor_gramps_id=NOT_A_REAL_GRMPS_ID"
        )
        self.assertEqual(rv.status_code, 200)
        self.assertNotIn(b"BEGIN:VEVENT", rv.data)

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
