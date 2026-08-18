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

"""Test that `register_endpt()` gives every OpenAPI operation a distinct id.

`register_endpt()` derives an operationId of `{verb}_{name}` from the
endpoint `name` every call site already passes, instead of each resource
having to derive one for itself. Without a distinct operationId, tools that
generate clients (or MCP servers) from the OpenAPI spec cannot tell
operations apart.
"""

import unittest

from gramps_webapi.app import create_app

# gramps_class_name -> (url path segment, singular route name, plural route name)
# The route names mirror the `name` argument passed to register_endpt() in
# gramps_webapi/api/__init__.py for that type's endpoints.
OBJECT_ROUTES = {
    "Person": ("people", "person", "people"),
    "Family": ("families", "family", "families"),
    "Event": ("events", "event", "events"),
    "Place": ("places", "place", "places"),
    "Citation": ("citations", "citation", "citations"),
    "Source": ("sources", "source", "sources"),
    "Repository": ("repositories", "repository", "repositories"),
    "Media": ("media", "media_object", "media_objects"),
    "Note": ("notes", "note", "notes"),
    "Tag": ("tags", "tag", "tags"),
}


class TestOpenapiOperationIds(unittest.TestCase):
    """Test operationId/requestBody documentation across the OpenAPI spec."""

    @classmethod
    def setUpClass(cls):
        """Set up a minimal app and fetch the live OpenAPI spec."""
        app = create_app(
            {"TREE": "test", "SECRET_KEY": "test", "USER_DB_URI": "sqlite://"},
            config_from_env=False,
        )
        with app.test_client() as client:
            response = client.get("/api/openapi.json")
            if response.status_code != 200:
                raise AssertionError(
                    f"Failed to fetch OpenAPI spec: {response.status_code}"
                )
            cls.spec = response.get_json()
            if cls.spec is None:
                raise AssertionError("OpenAPI spec returned non-JSON response")

    def _operation(self, path, method):
        methods = self.spec["paths"][path]
        return methods[method]

    def test_every_operation_has_a_unique_operation_id(self):
        """Every operation in the spec has a non-null, unique operationId."""
        operation_ids = [
            operation.get("operationId")
            for methods in self.spec["paths"].values()
            for method, operation in methods.items()
            if method in ("get", "post", "put", "delete", "patch")
        ]
        self.assertTrue(all(operation_ids), "Every operation needs an operationId")
        self.assertEqual(
            len(operation_ids),
            len(set(operation_ids)),
            "operationIds must be unique across the whole spec",
        )

    def test_object_crud_operation_ids_match_expected_names(self):
        """Object CRUD operationIds follow the `{verb}_{route_name}` scheme."""
        for gramps_class_name, (url_segment, singular, plural) in OBJECT_ROUTES.items():
            with self.subTest(gramps_class_name=gramps_class_name):
                self.assertEqual(
                    self._operation(f"/api/{url_segment}/{{handle}}", "get").get(
                        "operationId"
                    ),
                    f"get_{singular}",
                )
                self.assertEqual(
                    self._operation(f"/api/{url_segment}/{{handle}}", "put").get(
                        "operationId"
                    ),
                    f"put_{singular}",
                )
                self.assertEqual(
                    self._operation(f"/api/{url_segment}/{{handle}}", "delete").get(
                        "operationId"
                    ),
                    f"delete_{singular}",
                )
                self.assertEqual(
                    self._operation(f"/api/{url_segment}/", "get").get("operationId"),
                    f"get_{plural}",
                )
                self.assertEqual(
                    self._operation(f"/api/{url_segment}/", "post").get("operationId"),
                    f"post_{plural}",
                )

    def test_mutation_endpoints_document_a_request_body(self):
        """POST/PUT on object endpoints advertise the expected JSON payload."""
        for gramps_class_name, (url_segment, _, _) in OBJECT_ROUTES.items():
            with self.subTest(gramps_class_name=gramps_class_name):
                expected_ref = f"#/components/schemas/{gramps_class_name}"
                post_op = self._operation(f"/api/{url_segment}/", "post")
                if gramps_class_name != "Media":
                    # Media upload takes a raw file, not a JSON object.
                    self.assertEqual(
                        post_op["requestBody"]["content"]["application/json"]["schema"][
                            "$ref"
                        ],
                        expected_ref,
                    )
                else:
                    self.assertNotIn("requestBody", post_op)
                put_op = self._operation(f"/api/{url_segment}/{{handle}}", "put")
                self.assertEqual(
                    put_op["requestBody"]["content"]["application/json"]["schema"][
                        "$ref"
                    ],
                    expected_ref,
                )
