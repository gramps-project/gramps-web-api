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

import base64
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from flask import Flask
from pywebpush import WebPushException, webpush
from requests.exceptions import Timeout

from gramps_webapi.auth import (
    PushSubscription,
    get_guid,
    upsert_user_push_subscription,
    user_db,
)
from gramps_webapi.webpush import (
    _derive_vapid_key,
    get_web_push_config,
    send_web_push,
)

from . import get_test_client
from .test_push_subscriptions import AUTH, P256DH


class TestWebPushDelivery(unittest.TestCase):
    """Test delivery and stale subscription cleanup."""

    @classmethod
    def setUpClass(cls):
        cls.client = get_test_client()
        cls.app = cls.client.application

    def setUp(self):
        self.addCleanup(self.app.config.update, BASE_URL=self.app.config["BASE_URL"])
        self.app.config["BASE_URL"] = "https://gramps.example.test/"
        with self.app.app_context():
            user_db.session.query(PushSubscription).delete()
            user_db.session.commit()
            self.user_id = get_guid("owner")

    def _add_subscription(self):
        with self.app.app_context():
            upsert_user_push_subscription(
                user_id=self.user_id,
                endpoint="https://fcm.googleapis.com/subscription/1",
                p256dh=P256DH,
                auth=AUTH,
            )

    @patch("gramps_webapi.webpush.webpush")
    def test_sends_json_payload_with_vapid_configuration(self, mock_webpush):
        self._add_subscription()

        with self.app.app_context():
            send_web_push(
                self.user_id,
                {"title": "Gramps Web", "body": "A record changed"},
            )

        mock_webpush.assert_called_once()
        kwargs = mock_webpush.call_args.kwargs
        self.assertEqual(json.loads(kwargs["data"])["body"], "A record changed")
        with self.app.app_context():
            vapid, _, subject = get_web_push_config()
        self.assertIs(kwargs["vapid_private_key"], vapid)
        self.assertEqual(kwargs["vapid_claims"], {"sub": subject})
        self.assertNotIn("ttl", kwargs)
        self.assertEqual(kwargs["timeout"], 10)

    @patch("gramps_webapi.webpush.webpush")
    def test_removes_subscriptions_rejected_as_invalid_or_gone(self, mock_webpush):
        for status_code in (401, 403, 404, 410):
            with self.subTest(status_code=status_code):
                self._add_subscription()
                response = SimpleNamespace(status_code=status_code, text="Rejected")
                mock_webpush.side_effect = WebPushException(
                    "rejected", response=response
                )

                with self.app.app_context():
                    send_web_push(self.user_id, {"title": "Rejected"})
                    count = user_db.session.query(PushSubscription).count()

                self.assertEqual(count, 0)
                mock_webpush.reset_mock()

    @patch("gramps_webapi.webpush.webpush")
    def test_keeps_subscription_after_transient_failure(self, mock_webpush):
        self._add_subscription()
        response = SimpleNamespace(status_code=503, text="Unavailable")
        mock_webpush.side_effect = WebPushException("retry", response=response)

        with self.app.app_context():
            send_web_push(self.user_id, {"title": "Retry"})
            count = user_db.session.query(PushSubscription).count()

        self.assertEqual(count, 1)

    @patch("gramps_webapi.webpush.webpush")
    def test_skips_delivery_without_vapid_configuration(self, mock_webpush):
        self.app.config["BASE_URL"] = "http://localhost/"
        with self.app.app_context():
            send_web_push(self.user_id, {"title": "Unavailable"})
        mock_webpush.assert_not_called()

    @patch("gramps_webapi.webpush.webpush")
    def test_timeout_keeps_subscription_and_continues_delivery(self, mock_webpush):
        self._add_subscription()
        with self.app.app_context():
            upsert_user_push_subscription(
                user_id=self.user_id,
                endpoint="https://fcm.googleapis.com/subscription/2",
                p256dh=P256DH,
                auth=AUTH,
            )
            mock_webpush.side_effect = [Timeout(), None]
            send_web_push(self.user_id, {"title": "Retry later"})
            self.assertEqual(user_db.session.query(PushSubscription).count(), 2)
        self.assertEqual(mock_webpush.call_count, 2)


class TestWebPushConfig(unittest.TestCase):
    """Verify actual VAPID key derivation and signing, independently of delivery."""

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SECRET_KEY="test-only-stable-secret",
            BASE_URL="https://gramps.example.test:8443/gramps/",
        )

    def _config(self):
        with self.app.app_context():
            return get_web_push_config()

    def test_stable_public_key_and_verifiable_vapid_signature(self):
        vapid, public_key, subject = self._config()
        encoded = base64.urlsafe_b64decode(public_key + "=" * (-len(public_key) % 4))
        public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), encoded)
        self.assertEqual(len(encoded), 65)
        self.assertEqual(public.public_numbers(), vapid.public_key.public_numbers())
        self.assertEqual(subject, "https://gramps.example.test:8443")
        signed = vapid.sign({"sub": subject, "aud": "https://fcm.googleapis.com"})
        token = signed["Authorization"].split("t=", 1)[1].split(",", 1)[0]
        claims = jwt.decode(
            token, public, algorithms=["ES256"], audience="https://fcm.googleapis.com"
        )
        self.assertEqual(claims["sub"], subject)
        receiver = (
            ec.derive_private_key(2, ec.SECP256R1())
            .public_key()
            .public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
        )
        session = Mock()
        session.post.return_value.status_code = 201
        response = webpush(
            subscription_info={
                "endpoint": "https://fcm.googleapis.com/subscription/1",
                "keys": {
                    "p256dh": base64.urlsafe_b64encode(receiver)
                    .rstrip(b"=")
                    .decode("ascii"),
                    "auth": AUTH,
                },
            },
            data=json.dumps({"title": "Gramps Web"}),
            vapid_private_key=vapid,
            vapid_claims={"sub": subject},
            requests_session=session,
        )
        self.assertIs(response, session.post.return_value)
        self.assertEqual(
            session.post.call_args.kwargs["headers"]["content-encoding"], "aes128gcm"
        )
        self.assertIn(
            "vapid", session.post.call_args.kwargs["headers"]["authorization"]
        )
        _derive_vapid_key.cache_clear()
        self.assertEqual(self._config()[1], public_key)
        self.app.config["SECRET_KEY"] = self.app.config["SECRET_KEY"].encode("utf-8")
        self.assertEqual(self._config()[1], public_key)

    def test_secret_rotation_changes_key_but_base_url_does_not(self):
        _, original, _ = self._config()
        self.app.config["BASE_URL"] = "https://other.example.test/"
        self.assertEqual(self._config()[1], original)
        self.app.config["SECRET_KEY"] = "test-only-replacement-secret"
        self.assertNotEqual(self._config()[1], original)

    def test_unavailable_without_secret(self):
        self.app.config["SECRET_KEY"] = None
        self.assertIsNone(self._config())
