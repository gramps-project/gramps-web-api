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

"""Tests for current-user Web Push subscription endpoints."""

import base64
import time
import unittest

from gramps_webapi.auth import PushSubscription, get_guid, user_db
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER

from . import BASE_URL, get_test_client
from .util import fetch_header

PUSH_URL = BASE_URL + "/users/-/push-subscriptions/"
PUBLIC_KEY = base64.urlsafe_b64encode(b"\x04" + b"\x01" * 64).rstrip(b"=").decode()
P256DH = base64.urlsafe_b64encode(b"\x04" + b"\x02" * 64).rstrip(b"=").decode()
AUTH = base64.urlsafe_b64encode(b"\x03" * 16).rstrip(b"=").decode()


def subscription_payload(endpoint="https://push.example.test/subscription/1"):
    """Return a valid browser subscription payload."""
    return {
        "endpoint": endpoint,
        "expirationTime": None,
        "keys": {"p256dh": P256DH, "auth": AUTH},
    }


class TestPushSubscriptions(unittest.TestCase):
    """Test Web Push subscription lifecycle and ownership."""

    @classmethod
    def setUpClass(cls):
        cls.client = get_test_client()
        cls.app = cls.client.application

    def setUp(self):
        with self.app.app_context():
            user_db.session.query(PushSubscription).delete()
            user_db.session.commit()
        self.app.config.update(
            WEB_PUSH_VAPID_PUBLIC_KEY=PUBLIC_KEY,
            WEB_PUSH_VAPID_PRIVATE_KEY="test-private-key",
            WEB_PUSH_VAPID_SUBJECT="mailto:admin@example.test",
            WEB_PUSH_MAX_SUBSCRIPTIONS_PER_USER=20,
        )

    def test_requires_authentication(self):
        response = self.client.get(PUSH_URL)
        self.assertEqual(response.status_code, 401)

    def test_reports_unconfigured_server_without_exposing_endpoints(self):
        self.app.config["WEB_PUSH_VAPID_PRIVATE_KEY"] = ""
        header = fetch_header(self.client, role=ROLE_OWNER)

        response = self.client.get(PUSH_URL, headers=header)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json,
            {"available": False, "public_key": None, "subscriptions": 0},
        )
        response = self.client.post(
            PUSH_URL, headers=header, json=subscription_payload()
        )
        self.assertEqual(response.status_code, 503)

        self.app.config.update(
            WEB_PUSH_VAPID_PUBLIC_KEY="invalid",
            WEB_PUSH_VAPID_PRIVATE_KEY="test-private-key",
        )
        response = self.client.get(PUSH_URL, headers=header)
        self.assertEqual(
            response.json,
            {"available": False, "public_key": None, "subscriptions": 0},
        )

    def test_creates_and_updates_subscription_without_returning_secrets(self):
        header = fetch_header(self.client, role=ROLE_OWNER)
        payload = subscription_payload()

        response = self.client.post(PUSH_URL, headers=header, json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["subscriptions"], 1)
        self.assertEqual(response.json["public_key"], PUBLIC_KEY)
        self.assertNotIn("endpoint", response.json)
        self.assertNotIn("keys", response.json)

        updated = subscription_payload()
        updated["keys"]["auth"] = (
            base64.urlsafe_b64encode(b"\x04" * 16).rstrip(b"=").decode()
        )
        response = self.client.post(PUSH_URL, headers=header, json=updated)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["subscriptions"], 1)

        with self.app.app_context():
            row = user_db.session.query(PushSubscription).one()
            self.assertEqual(row.endpoint, payload["endpoint"])
            self.assertEqual(row.auth, updated["keys"]["auth"])
            self.assertEqual(len(row.endpoint_hash), 64)
            self.assertNotEqual(row.endpoint_hash, row.endpoint)

    def test_subscription_ownership_moves_with_the_browser(self):
        owner_header = fetch_header(self.client, role=ROLE_OWNER)
        guest_header = fetch_header(self.client, role=ROLE_GUEST)
        payload = subscription_payload()
        self.client.post(PUSH_URL, headers=owner_header, json=payload)

        response = self.client.post(PUSH_URL, headers=guest_header, json=payload)

        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            row = user_db.session.query(PushSubscription).one()
            self.assertEqual(row.user_id, get_guid("guest"))

    def test_delete_is_idempotent_and_limited_to_current_user(self):
        owner_header = fetch_header(self.client, role=ROLE_OWNER)
        guest_header = fetch_header(self.client, role=ROLE_GUEST)
        payload = subscription_payload()
        self.client.post(PUSH_URL, headers=owner_header, json=payload)

        delete_payload = {"endpoint": payload["endpoint"]}
        response = self.client.delete(
            PUSH_URL, headers=guest_header, json=delete_payload
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["subscriptions"], 0)
        with self.app.app_context():
            self.assertEqual(user_db.session.query(PushSubscription).count(), 1)

        response = self.client.delete(
            PUSH_URL, headers=owner_header, json=delete_payload
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["subscriptions"], 0)
        response = self.client.delete(
            PUSH_URL, headers=owner_header, json=delete_payload
        )
        self.assertEqual(response.status_code, 200)

    def test_rejects_invalid_or_expired_subscriptions(self):
        header = fetch_header(self.client, role=ROLE_OWNER)
        for endpoint in (
            "http://push.example.test/push",
            "https://127.0.0.1/push",
            "https://localhost/push",
            "https://user:password@push.example.test/push",
        ):
            response = self.client.post(
                PUSH_URL,
                headers=header,
                json=subscription_payload(endpoint),
            )
            self.assertEqual(response.status_code, 422)

        invalid_key = subscription_payload()
        invalid_key["keys"]["auth"] = "invalid"
        response = self.client.post(PUSH_URL, headers=header, json=invalid_key)
        self.assertEqual(response.status_code, 422)

        invalid_public_key = subscription_payload()
        invalid_public_key["keys"]["p256dh"] = (
            base64.urlsafe_b64encode(b"\x03" * 65).rstrip(b"=").decode()
        )
        response = self.client.post(PUSH_URL, headers=header, json=invalid_public_key)
        self.assertEqual(response.status_code, 422)

        expired = subscription_payload()
        expired["expirationTime"] = int(time.time() * 1000) - 1
        response = self.client.post(PUSH_URL, headers=header, json=expired)
        self.assertEqual(response.status_code, 422)

    def test_enforces_per_user_subscription_limit(self):
        self.app.config["WEB_PUSH_MAX_SUBSCRIPTIONS_PER_USER"] = 1
        header = fetch_header(self.client, role=ROLE_OWNER)
        first = subscription_payload("https://push.example.test/subscription/1")
        second = subscription_payload("https://push.example.test/subscription/2")
        self.assertEqual(
            self.client.post(PUSH_URL, headers=header, json=first).status_code,
            200,
        )

        response = self.client.post(PUSH_URL, headers=header, json=second)

        self.assertEqual(response.status_code, 409)
