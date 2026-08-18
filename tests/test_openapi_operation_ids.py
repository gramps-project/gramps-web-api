#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Jerome Viveret
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

"""Test that the generic object CRUD endpoints have distinct OpenAPI operationIds.

The generic get/post/put/delete methods for Person, Family, Event, ... are
defined once in `GrampsObjectResource`/`GrampsObjectsResource` and inherited
unchanged by every object type. Without per-type operationIds, tools that
generate clients (or MCP servers) from the OpenAPI spec cannot tell the
generated operations apart.
"""

import unittest

from gramps_webapi.app import create_app
from gramps_webapi.const import GRAMPS_OBJECT_PLURAL


class TestOpenapiOperationIds(unittest.TestCase):
    """Test operationId/requestBody documentation for the object CRUD endpoints."""

    @classmethod
    def setUpClass(cls):
        """Set up a minimal app and fetch the live OpenAPI spec."""
        app = create_app(
            {"TREE": "test", "SECRET_KEY": "test", "USER_DB_URI": "sqlite://"},
            config_from_env=False,
        )
        with app.test_client() as client:
            response = client.get("/api/openapi.json")
            assert (
                response.status_code == 200
            ), f"Failed to fetch OpenAPI spec: {response.status_code}"
            cls.spec = response.get_json()
            assert cls.spec is not None, "OpenAPI spec returned non-JSON response"

    def _operation(self, path, method):
        methods = self.spec["paths"][path]
        return methods[method]

    def test_operation_ids_are_unique_per_object_type(self):
        """Every object type's CRUD operations get a distinct operationId."""
        operation_ids = []
        for gramps_class_name, plural in GRAMPS_OBJECT_PLURAL.items():
            operation_ids.append(
                self._operation(f"/api/{plural}/", "get").get("operationId")
            )
            operation_ids.append(
                self._operation(f"/api/{plural}/", "post").get("operationId")
            )
            operation_ids.append(
                self._operation(f"/api/{plural}/{{handle}}", "get").get(
                    "operationId"
                )
            )
            operation_ids.append(
                self._operation(f"/api/{plural}/{{handle}}", "put").get(
                    "operationId"
                )
            )
            operation_ids.append(
                self._operation(f"/api/{plural}/{{handle}}", "delete").get(
                    "operationId"
                )
            )
        self.assertTrue(all(operation_ids), "Every CRUD operation needs an operationId")
        self.assertEqual(
            len(operation_ids),
            len(set(operation_ids)),
            "operationIds must be unique across object types",
        )

    def test_mutation_endpoints_document_a_request_body(self):
        """POST/PUT on object endpoints advertise the expected JSON payload."""
        for gramps_class_name, plural in GRAMPS_OBJECT_PLURAL.items():
            with self.subTest(gramps_class_name=gramps_class_name):
                post_op = self._operation(f"/api/{plural}/", "post")
                if gramps_class_name == "Media":
                    # Media upload takes a raw file, not a JSON object.
                    continue
                self.assertIn("requestBody", post_op)
                put_op = self._operation(f"/api/{plural}/{{handle}}", "put")
                self.assertIn("requestBody", put_op)
