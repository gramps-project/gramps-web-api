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

"""Test the PROXY_FIX_X_FOR option, which sets the rate limiting key."""

import unittest
from unittest.mock import patch

from flask_limiter.util import get_remote_address
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.dbstate import DbState

from gramps_webapi.app import create_app
from gramps_webapi.const import ENV_CONFIG_FILE, TEST_AUTH_CONFIG

SOCKET_ADDR = "10.0.0.1"
CLIENT_ADDR = "203.0.113.7"


def _make_client(config):
    with patch.dict("os.environ", {ENV_CONFIG_FILE: TEST_AUTH_CONFIG}):
        app = create_app(
            config={"TESTING": True, **config},
            config_from_env=False,
        )
    # expose the key the IP-based rate limiter uses
    app.add_url_rule("/test-rate-limit-key", "rate_limit_key", get_remote_address)
    return app.test_client()


class TestProxyFix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "Test Web API test_proxy_fix"
        cls.dbman = CLIDbManager(DbState())
        cls.dbman.create_new_db_cli(cls.name, dbid="sqlite")

    @classmethod
    def tearDownClass(cls):
        cls.dbman.remove_database(cls.name)

    def _get_key(self, client, headers):
        rv = client.get(
            "/test-rate-limit-key",
            headers=headers,
            environ_base={"REMOTE_ADDR": SOCKET_ADDR},
        )
        assert rv.status_code == 200
        return rv.get_data(as_text=True)

    def test_unset_ignores_forwarded_for(self):
        client = _make_client({})
        headers = {"X-Forwarded-For": CLIENT_ADDR}
        assert self._get_key(client, headers) == SOCKET_ADDR

    def test_one_proxy_uses_forwarded_for(self):
        client = _make_client({"PROXY_FIX_X_FOR": 1})
        headers = {"X-Forwarded-For": CLIENT_ADDR}
        assert self._get_key(client, headers) == CLIENT_ADDR

    def test_one_proxy_ignores_spoofed_entries(self):
        """Only the entry added by the trusted proxy counts."""
        client = _make_client({"PROXY_FIX_X_FOR": 1})
        headers = {"X-Forwarded-For": f"1.2.3.4, {CLIENT_ADDR}"}
        assert self._get_key(client, headers) == CLIENT_ADDR

    def test_one_proxy_without_header(self):
        client = _make_client({"PROXY_FIX_X_FOR": 1})
        assert self._get_key(client, {}) == SOCKET_ADDR

    def test_string_value(self):
        """A value read from a config file can be a string."""
        client = _make_client({"PROXY_FIX_X_FOR": "1"})
        headers = {"X-Forwarded-For": CLIENT_ADDR}
        assert self._get_key(client, headers) == CLIENT_ADDR
