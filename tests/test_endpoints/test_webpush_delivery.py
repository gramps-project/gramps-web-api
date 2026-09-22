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

"""Tests for the reusable Web Push delivery helper."""

import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pywebpush import WebPushException

from gramps_webapi.auth import (
    PushSubscription,
    get_guid,
    upsert_user_push_subscription,
    user_db,
)
from gramps_webapi.webpush import WebPushNotConfiguredError, send_web_push

from . import get_test_client
from .test_push_subscriptions import AUTH, P256DH


class TestWebPushDelivery(unittest.TestCase):
    """Test delivery summaries and stale subscription cleanup."""

    @classmethod
    def setUpClass(cls):
        cls.client = get_test_client()
        cls.app = cls.client.application

    def setUp(self):
        self.app.config.update(
            WEB_PUSH_VAPID_PUBLIC_KEY="test-public-key",
            WEB_PUSH_VAPID_PRIVATE_KEY="test-private-key",
            WEB_PUSH_VAPID_SUBJECT="mailto:admin@example.test",
            WEB_PUSH_MAX_PAYLOAD_BYTES=3072,
            WEB_PUSH_TTL=3600,
            WEB_PUSH_TIMEOUT=5,
        )
        with self.app.app_context():
            user_db.session.query(PushSubscription).delete()
            user_db.session.commit()
            self.user_id = get_guid("owner")

    def _add_subscription(self, expiration_time=None):
        with self.app.app_context():
            upsert_user_push_subscription(
                username="owner",
                endpoint="https://push.example.test/subscription/1",
                p256dh=P256DH,
                auth=AUTH,
                expiration_time=expiration_time,
            )

    @patch("gramps_webapi.webpush.webpush")
    def test_sends_json_payload_with_vapid_configuration(self, mock_webpush):
        self._add_subscription()

        with self.app.app_context():
            result = send_web_push(
                self.user_id,
                {"title": "Gramps Web", "body": "A record changed"},
            )

        self.assertEqual(result.sent, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.removed, 0)
        kwargs = mock_webpush.call_args.kwargs
        self.assertEqual(json.loads(kwargs["data"])["body"], "A record changed")
        self.assertEqual(kwargs["vapid_private_key"], "test-private-key")
        self.assertEqual(kwargs["vapid_claims"], {"sub": "mailto:admin@example.test"})
        self.assertEqual(kwargs["ttl"], 3600)
        self.assertEqual(kwargs["timeout"], 5)

    @patch("gramps_webapi.webpush.webpush")
    def test_removes_expired_subscription_without_delivery(self, mock_webpush):
        self._add_subscription(expiration_time=int(time.time() * 1000) - 1)

        with self.app.app_context():
            result = send_web_push(self.user_id, {"title": "Expired"})
            count = user_db.session.query(PushSubscription).count()

        self.assertEqual(result.removed, 1)
        self.assertEqual(count, 0)
        mock_webpush.assert_not_called()

    @patch("gramps_webapi.webpush.webpush")
    def test_removes_subscription_rejected_as_gone(self, mock_webpush):
        self._add_subscription()
        response = SimpleNamespace(status_code=410, text="Gone")
        mock_webpush.side_effect = WebPushException("gone", response=response)

        with self.app.app_context():
            result = send_web_push(self.user_id, {"title": "Gone"})
            count = user_db.session.query(PushSubscription).count()

        self.assertEqual(result.removed, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(count, 0)

    @patch("gramps_webapi.webpush.webpush")
    def test_keeps_subscription_after_transient_failure(self, mock_webpush):
        self._add_subscription()
        response = SimpleNamespace(status_code=503, text="Unavailable")
        mock_webpush.side_effect = WebPushException("retry", response=response)

        with self.app.app_context():
            result = send_web_push(self.user_id, {"title": "Retry"})
            count = user_db.session.query(PushSubscription).count()

        self.assertEqual(result.failed, 1)
        self.assertEqual(result.removed, 0)
        self.assertEqual(count, 1)

    def test_requires_vapid_configuration(self):
        self.app.config["WEB_PUSH_VAPID_PRIVATE_KEY"] = ""
        with self.app.app_context():
            with self.assertRaises(WebPushNotConfiguredError):
                send_web_push(self.user_id, {"title": "Unavailable"})

    def test_rejects_oversized_payload(self):
        self.app.config["WEB_PUSH_MAX_PAYLOAD_BYTES"] = 10
        with self.app.app_context():
            with self.assertRaises(ValueError):
                send_web_push(self.user_id, {"body": "too large"})
