#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Doug Blank
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

import requests
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any


class Client:
    """Client for Gramps Web API with programmatic login support."""

    def __init__(self, api_host: str):
        """
        Initialize the client.

        Args:
            api_host: Base URL of the API (e.g., "http://localhost:5000")
        """
        self.api_host = api_host.rstrip("/")
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None

    def login(
        self, username: str, password: str, redirect: str = "/"
    ) -> Dict[str, str]:
        """
        Log in programmatically.

        Args:
            username: Username
            password: Password
            redirect: Optional redirect path (default: "/")

        Returns:
            Dictionary with access_token and refresh_token

        Raises:
            requests.HTTPError: If login fails
        """
        # Step 1: POST credentials
        response = requests.post(
            f"{self.api_host}/api/login/",
            json={"username": username, "password": password, "redirect": redirect},
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

        # Step 2: Extract token from redirect URL
        redirect_url = response.json()["redirect_url"]
        parsed_url = urlparse(redirect_url)
        query_params = parse_qs(parsed_url.query)
        token = query_params.get("token", [None])[0]

        if not token:
            raise ValueError("No token found in redirect URL")

        # Step 3: Exchange token for real tokens
        token_response = requests.get(
            f"{self.api_host}/api/login/token/",
            params={"token": token},
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()

        # Step 4: Store tokens
        tokens = token_response.json()
        self.access_token = tokens["access_token"]
        self.refresh_token = tokens.get("refresh_token")

        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
        }

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with authentication."""
        headers = {"Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def get(self, endpoint: str, **kwargs) -> Any:
        """Make a GET request."""
        if not self.access_token:
            raise ValueError("Not logged in. Call login() first.")
        response = requests.get(
            f"{self.api_host}{endpoint}", headers=self._get_headers(), **kwargs
        )
        response.raise_for_status()
        return response.json()

    def post(self, endpoint: str, data: Any = None, json: Any = None, **kwargs) -> Any:
        """Make a POST request."""
        if not self.access_token:
            raise ValueError("Not logged in. Call login() first.")
        headers = self._get_headers()
        if json is not None:
            headers["Content-Type"] = "application/json"
        response = requests.post(
            f"{self.api_host}{endpoint}",
            headers=headers,
            data=data,
            json=json,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    def put(self, endpoint: str, data: Any = None, json: Any = None, **kwargs) -> Any:
        """Make a PUT request."""
        if not self.access_token:
            raise ValueError("Not logged in. Call login() first.")
        headers = self._get_headers()
        if json is not None:
            headers["Content-Type"] = "application/json"
        response = requests.put(
            f"{self.api_host}{endpoint}",
            headers=headers,
            data=data,
            json=json,
            **kwargs,
        )
        response.raise_for_status()
        return response.json()

    def delete(self, endpoint: str, **kwargs) -> Any:
        """Make a DELETE request."""
        if not self.access_token:
            raise ValueError("Not logged in. Call login() first.")
        response = requests.delete(
            f"{self.api_host}{endpoint}", headers=self._get_headers(), **kwargs
        )
        response.raise_for_status()
        return response.json() if response.content else None
