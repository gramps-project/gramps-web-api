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
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Tests for linking an OIDC identity to an existing user."""

import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from flask import redirect

from gramps_webapi.auth import (
    add_user,
    create_oidc_account,
    get_guid,
    get_oidc_account,
    get_user_details,
    modify_user,
)
from gramps_webapi.auth.const import ROLE_DISABLED, ROLE_EDITOR

from . import BASE_URL, get_test_client

LINK_URL = BASE_URL + "/oidc/link/"
LOGIN_URL = BASE_URL + "/oidc/login/"
CALLBACK_URL = BASE_URL + "/oidc/callback/custom"
OIDC = "gramps_webapi.api.resources.oidc"


class TestOIDCLink(unittest.TestCase):
    """Test cases for /oidc/link/ and the link mode of login and callback."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.app = get_test_client().application

    def setUp(self):
        """Mock a configured provider and start each test in a new browser."""
        self.oidc_client = MagicMock()
        self.oidc_client.authorize_redirect.return_value = redirect(
            "https://idp.example.org/authorize"
        )
        self.oidc_client.authorize_access_token.return_value = {"access_token": "x"}
        oauth = MagicMock()
        oauth.gramps_custom = self.oidc_client
        for patcher in (
            patch(f"{OIDC}.is_oidc_enabled", return_value=True),
            patch(f"{OIDC}.get_available_oidc_providers", return_value=["custom"]),
            patch(f"{OIDC}.get_provider_config", return_value={"name": "Custom"}),
            patch(f"{OIDC}.configure_pkce", return_value=False),
            patch.dict(
                self.app.extensions, {"authlib.integrations.flask_client": oauth}
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.browser = self.app.test_client()
        self.user = self._add_user()

    def _add_user(self, role=ROLE_EDITOR):
        """Add a local user in the owner's tree and return its name."""
        name = f"link-{uuid4().hex[:8]}"
        with self.app.app_context():
            tree = get_user_details("owner")["tree"]
            add_user(name=name, password="secret", role=role, tree=tree)
        return name

    def _guid(self, name):
        with self.app.app_context():
            return str(get_guid(name))

    def _header(self, browser, name, fresh=True):
        """Log in as name and return an authorization header."""
        rv = browser.post(
            BASE_URL + "/token/", json={"username": name, "password": "secret"}
        )
        self.assertEqual(rv.status_code, 200)
        if fresh:
            return {"Authorization": f"Bearer {rv.json['access_token']}"}
        rv = browser.post(
            BASE_URL + "/token/refresh/",
            headers={"Authorization": f"Bearer {rv.json['refresh_token']}"},
        )
        return {"Authorization": f"Bearer {rv.json['access_token']}"}

    def _ticket(self, browser=None, name=None, provider="custom"):
        browser = browser or self.browser
        rv = browser.post(
            LINK_URL,
            headers=self._header(browser, name or self.user),
            json={"provider": provider},
        )
        self.assertEqual(rv.status_code, 200)
        return rv.json["ticket"]

    def _callback(self, sub, browser=None):
        """Complete the round trip to the provider as the identity sub."""
        self.oidc_client.userinfo.return_value = {"sub": sub, "email": "l@example.org"}
        return (browser or self.browser).get(CALLBACK_URL + "?code=c&state=s")

    def _link(self, sub, browser=None):
        """Run a whole link and return the callback response."""
        browser = browser or self.browser
        ticket = self._ticket(browser)
        rv = browser.get(f"{LOGIN_URL}?provider=custom&link={ticket}")
        self.assertEqual(rv.status_code, 302)
        return self._callback(sub, browser)

    def _owner(self, sub):
        with self.app.app_context():
            owner = get_oidc_account("custom", sub)
        return None if owner is None else str(owner)

    def test_identity_is_linked_to_the_ticket_user(self):
        sub = f"sub-{uuid4().hex}"
        rv = self._link(sub)
        self.assertEqual(rv.status_code, 302)
        self.assertTrue(rv.location.endswith("/oidc/complete#linked=custom"))
        self.assertEqual(self._owner(sub), self._guid(self.user))

    def test_linking_issues_no_tokens_and_leaves_the_user_alone(self):
        with self.app.app_context():
            before = get_user_details(self.user)
        with (
            patch(f"{OIDC}.create_or_update_oidc_user") as login,
            patch(f"{OIDC}.get_tokens") as tokens,
        ):
            rv = self._link(f"sub-{uuid4().hex}")
        login.assert_not_called()
        tokens.assert_not_called()
        self.assertNotIn("code=", rv.location)
        with self.app.app_context():
            self.assertEqual(get_user_details(self.user), before)

    def test_identity_of_another_user_is_refused(self):
        sub = f"sub-{uuid4().hex}"
        other = self._add_user()
        with self.app.app_context():
            create_oidc_account(get_guid(other), "custom", sub)
        rv = self._link(sub)
        self.assertTrue(rv.location.endswith("#error=identity_in_use"))
        self.assertEqual(self._owner(sub), self._guid(other))

    def test_identity_already_linked_to_the_same_user(self):
        sub = f"sub-{uuid4().hex}"
        self._link(sub)
        rv = self._link(sub)
        self.assertTrue(rv.location.endswith("#linked=custom"))

    def test_link_needs_a_fresh_login(self):
        rv = self.browser.post(
            LINK_URL,
            headers=self._header(self.browser, self.user, fresh=False),
            json={"provider": "custom"},
        )
        self.assertEqual(rv.status_code, 401)

    def test_unknown_provider_is_refused(self):
        rv = self.browser.post(
            LINK_URL,
            headers=self._header(self.browser, self.user),
            json={"provider": "nope"},
        )
        self.assertEqual(rv.status_code, 400)

    def test_ticket_from_another_browser_is_refused(self):
        """A ticket sent to someone else can't link their identity."""
        ticket = self._ticket()
        victim = self.app.test_client()
        rv = victim.get(f"{LOGIN_URL}?provider=custom&link={ticket}")
        self.assertEqual(rv.status_code, 403)
        self.oidc_client.authorize_redirect.assert_not_called()

    def test_ticket_works_only_once(self):
        ticket = self._ticket()
        with self.browser.session_transaction() as sess:
            nonce = sess["oidc_link_nonce"]
        url = f"{LOGIN_URL}?provider=custom&link={ticket}"
        self.assertEqual(self.browser.get(url).status_code, 302)
        with self.browser.session_transaction() as sess:
            # even with the browser binding restored, the ticket itself is spent
            sess["oidc_link_nonce"] = nonce
        rv = self.browser.get(url)
        self.assertEqual(rv.status_code, 400)
        self.assertIn("already been used", rv.json["error"]["message"])

    def test_ticket_for_another_provider_is_refused(self):
        ticket = self._ticket()
        with patch(
            f"{OIDC}.get_available_oidc_providers", return_value=["custom", "google"]
        ):
            self.app.extensions["authlib.integrations.flask_client"].gramps_google = (
                self.oidc_client
            )
            rv = self.browser.get(f"{LOGIN_URL}?provider=google&link={ticket}")
        self.assertEqual(rv.status_code, 400)

    def test_expired_ticket_is_refused(self):
        ticket = self._ticket()
        with patch(f"{OIDC}.OIDC_LINK_TICKET_TIMEOUT", -1):
            rv = self.browser.get(f"{LOGIN_URL}?provider=custom&link={ticket}")
        self.assertEqual(rv.status_code, 400)
        self.assertIn("expired", rv.json["error"]["message"])

    def test_tampered_ticket_is_refused(self):
        ticket = self._ticket()
        rv = self.browser.get(f"{LOGIN_URL}?provider=custom&link={ticket}x")
        self.assertEqual(rv.status_code, 400)

    def test_plain_login_after_an_unfinished_link_logs_in(self):
        """A link abandoned at the provider must not hijack the next login."""
        ticket = self._ticket()
        self.browser.get(f"{LOGIN_URL}?provider=custom&link={ticket}")
        with self.app.app_context():
            tree = get_user_details("owner")["tree"]
        rv = self.browser.get(f"{LOGIN_URL}?provider=custom&tree={tree}")
        self.assertEqual(rv.status_code, 302)
        with self.browser.session_transaction() as sess:
            self.assertNotIn("oidc_link", sess)
        sub = f"sub-{uuid4().hex}"
        with patch(
            f"{OIDC}.create_or_update_oidc_user", side_effect=ValueError("login")
        ) as login:
            self._callback(sub)
        login.assert_called_once()
        self.assertIsNone(self._owner(sub))

    def test_provider_error_is_reported_in_the_fragment(self):
        ticket = self._ticket()
        self.browser.get(f"{LOGIN_URL}?provider=custom&link={ticket}")
        self.oidc_client.authorize_access_token.side_effect = Exception("denied")
        rv = self.browser.get(CALLBACK_URL + "?error=access_denied")
        self.assertEqual(rv.status_code, 302)
        self.assertTrue(rv.location.endswith("#error=link_failed"))

    def test_user_disabled_meanwhile_is_not_linked(self):
        sub = f"sub-{uuid4().hex}"
        ticket = self._ticket()
        self.browser.get(f"{LOGIN_URL}?provider=custom&link={ticket}")
        with self.app.app_context():
            modify_user(name=self.user, role=ROLE_DISABLED)
        rv = self._callback(sub)
        self.assertTrue(rv.location.endswith("#error=link_failed"))
        self.assertIsNone(self._owner(sub))

    def test_missing_sub_is_not_linked(self):
        ticket = self._ticket()
        self.browser.get(f"{LOGIN_URL}?provider=custom&link={ticket}")
        self.oidc_client.userinfo.return_value = {"email": "l@example.org"}
        rv = self.browser.get(CALLBACK_URL + "?code=c&state=s")
        self.assertTrue(rv.location.endswith("#error=link_failed"))
