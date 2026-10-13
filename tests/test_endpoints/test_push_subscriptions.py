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
import unittest
from hashlib import sha256
from unittest.mock import patch

from sqlalchemy.exc import IntegrityError

from gramps_webapi.auth import (
    PushSubscription,
    get_guid,
    upsert_user_push_subscription,
    user_db,
)
from gramps_webapi.auth.const import ROLE_GUEST, ROLE_OWNER
from gramps_webapi.webpush import get_web_push_config

from . import BASE_URL, get_test_client
from .util import fetch_header

PUSH_URL = BASE_URL + "/users/-/push-subscriptions/"
P256DH = base64.urlsafe_b64encode(b"\x04" + b"\x02" * 64).rstrip(b"=").decode()
AUTH = base64.urlsafe_b64encode(b"\x03" * 16).rstrip(b"=").decode()


def subscription_payload(endpoint="https://fcm.googleapis.com/subscription/1"):
    """Return a valid browser subscription payload."""
    return {
        "endpoint": endpoint,
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
        self.addCleanup(self.app.config.update, BASE_URL=self.app.config["BASE_URL"])
        self.app.config["BASE_URL"] = "https://gramps.example.test/"

    def test_requires_authentication(self):
        response = self.client.get(PUSH_URL)
        self.assertEqual(response.status_code, 401)

    def test_reports_unconfigured_server_without_exposing_endpoints(self):
        header = fetch_header(self.client, role=ROLE_OWNER)
        for base_url in (
            None,
            "http://localhost/",
            "https://",
            "not a URL",
            "https://[",
        ):
            with self.subTest(base_url=base_url):
                self.app.config["BASE_URL"] = base_url
                response = self.client.get(PUSH_URL, headers=header)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json, {"public_key": None})
                response = self.client.post(
                    PUSH_URL, headers=header, json=subscription_payload()
                )
                self.assertEqual(response.status_code, 503)

    def test_returns_only_the_generated_public_key(self):
        header = fetch_header(self.client, role=ROLE_OWNER)

        response = self.client.get(PUSH_URL, headers=header)

        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            config = get_web_push_config()
        self.assertIsNotNone(config)
        self.assertEqual(response.json, {"public_key": config[1]})

    def test_creates_and_updates_subscription_without_returning_secrets(self):
        header = fetch_header(self.client, role=ROLE_OWNER)
        payload = subscription_payload()

        response = self.client.post(PUSH_URL, headers=header, json=payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data, b"")

        updated = subscription_payload()
        updated["keys"]["auth"] = (
            base64.urlsafe_b64encode(b"\x04" * 16).rstrip(b"=").decode()
        )
        response = self.client.post(PUSH_URL, headers=header, json=updated)
        self.assertEqual(response.status_code, 201)

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

        self.assertEqual(response.status_code, 201)
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
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.data, b"")

        for endpoint in ("", "not-a-url", "http://localhost/obsolete"):
            response = self.client.delete(
                PUSH_URL, headers=owner_header, json={"endpoint": endpoint}
            )
            self.assertEqual(response.status_code, 204)
        for payload in ({}, {"endpoint": 123}):
            response = self.client.delete(PUSH_URL, headers=owner_header, json=payload)
            self.assertEqual(response.status_code, 422)
        with self.app.app_context():
            self.assertEqual(user_db.session.query(PushSubscription).count(), 1)

        response = self.client.delete(
            PUSH_URL, headers=owner_header, json=delete_payload
        )
        self.assertEqual(response.status_code, 204)
        response = self.client.delete(
            PUSH_URL, headers=owner_header, json=delete_payload
        )
        self.assertEqual(response.status_code, 204)

    def test_rejects_invalid_subscriptions(self):
        header = fetch_header(self.client, role=ROLE_OWNER)
        for endpoint in (
            "http://fcm.googleapis.com/push",
            "https://127.0.0.1/push",
            "https://localhost/push",
            "https://user:password@fcm.googleapis.com/push",
            "https://fcm.googleapis.com.evil.example/push",
            "https://evilfcm.googleapis.com/push",
            "https://push.services.mozilla.com/push",
            "https://updates.push.services.mozilla.com.evil.test/push",
            "https://[",
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

    def test_accepts_supported_push_service_hosts(self):
        header = fetch_header(self.client, role=ROLE_OWNER)
        endpoints = (
            "https://fcm.googleapis.com/subscription/1",
            "https://updates.push.services.mozilla.com/wpush/v2/1",
            "https://web.push.apple.com/subscription/1",
            "https://wus2.notify.windows.com/subscription/1",
        )

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(
                    PUSH_URL,
                    headers=header,
                    json=subscription_payload(endpoint),
                )
                self.assertEqual(response.status_code, 201)

    def test_enforces_per_user_subscription_limit(self):
        header = fetch_header(self.client, role=ROLE_OWNER)
        first = subscription_payload("https://fcm.googleapis.com/subscription/1")
        second = subscription_payload("https://fcm.googleapis.com/subscription/2")
        third = subscription_payload("https://fcm.googleapis.com/subscription/3")

        with patch("gramps_webapi.auth.MAX_PUSH_SUBSCRIPTIONS_PER_USER", 2):
            self.assertEqual(
                self.client.post(PUSH_URL, headers=header, json=first).status_code,
                201,
            )
            self.assertEqual(
                self.client.post(PUSH_URL, headers=header, json=second).status_code,
                201,
            )
            with self.app.app_context():
                first_id = (
                    user_db.session.query(PushSubscription)
                    .filter_by(endpoint=first["endpoint"])
                    .one()
                    .id
                )
            self.assertEqual(
                self.client.post(PUSH_URL, headers=header, json=first).status_code,
                201,
            )
            with self.app.app_context():
                self.assertEqual(user_db.session.query(PushSubscription).count(), 2)
                self.assertEqual(
                    user_db.session.query(PushSubscription)
                    .filter_by(endpoint=first["endpoint"])
                    .one()
                    .id,
                    first_id,
                )
            response = self.client.post(PUSH_URL, headers=header, json=third)

        self.assertEqual(response.status_code, 201)
        with self.app.app_context():
            endpoints = {
                row.endpoint for row in user_db.session.query(PushSubscription).all()
            }
            self.assertEqual(endpoints, {second["endpoint"], third["endpoint"]})

    def test_transfer_at_limit_evicts_oldest_subscription_from_new_owner(self):
        owner_header = fetch_header(self.client, role=ROLE_OWNER)
        guest_header = fetch_header(self.client, role=ROLE_GUEST)
        owner_endpoint = subscription_payload(
            "https://fcm.googleapis.com/subscription/owner"
        )
        guest_endpoint = subscription_payload(
            "https://fcm.googleapis.com/subscription/guest"
        )

        with patch("gramps_webapi.auth.MAX_PUSH_SUBSCRIPTIONS_PER_USER", 1):
            self.assertEqual(
                self.client.post(
                    PUSH_URL, headers=owner_header, json=owner_endpoint
                ).status_code,
                201,
            )
            self.assertEqual(
                self.client.post(
                    PUSH_URL, headers=guest_header, json=guest_endpoint
                ).status_code,
                201,
            )
            response = self.client.post(
                PUSH_URL, headers=guest_header, json=owner_endpoint
            )

        self.assertEqual(response.status_code, 201)
        with self.app.app_context():
            rows = user_db.session.query(PushSubscription).all()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].user_id, get_guid("guest"))
            self.assertEqual(rows[0].endpoint, owner_endpoint["endpoint"])

    def test_retries_when_concurrent_insert_wins_endpoint_unique_constraint(self):
        endpoint = "https://fcm.googleapis.com/subscription/concurrent"
        payload = subscription_payload(endpoint)
        commit_calls = 0

        with self.app.app_context():
            owner_id = get_guid("owner")
            real_commit = user_db.session.commit

            def commit_with_concurrent_insert():
                nonlocal commit_calls
                commit_calls += 1
                if commit_calls == 1:
                    user_db.session.rollback()
                    user_db.session.add(
                        PushSubscription(
                            user_id=owner_id,
                            endpoint=endpoint,
                            endpoint_hash=sha256(endpoint.encode("utf-8")).hexdigest(),
                            p256dh=P256DH,
                            auth=AUTH,
                        )
                    )
                    real_commit()
                    raise IntegrityError("INSERT", {}, Exception("duplicate endpoint"))
                real_commit()

            with patch(
                "gramps_webapi.auth.user_db.session.commit",
                side_effect=commit_with_concurrent_insert,
            ):
                upsert_user_push_subscription(
                    owner_id,
                    endpoint,
                    payload["keys"]["p256dh"],
                    AUTH,
                )
            row = user_db.session.query(PushSubscription).one()
            self.assertEqual(row.endpoint, endpoint)
            self.assertEqual(row.user_id, owner_id)
            self.assertEqual(row.auth, AUTH)
        self.assertEqual(commit_calls, 2)
