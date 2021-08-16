#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
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

"""Check functions for performing specific unit tests."""

from jsonschema import validate

from gramps_webapi.auth.const import ROLE_OWNER

from . import API_RESOLVER, API_SCHEMA
from .util import check_keys_stripped, fetch_header


def check_success(test, url, full=False, role=ROLE_OWNER):
    """Test that result returned successfully."""
    header = fetch_header(test.client, role=role)
    rv = test.client.get(url, headers=header)
    test.assertEqual(rv.status_code, 200)
    if not full:
        return rv.json
    return rv


def check_invalid_syntax(test, url, role=ROLE_OWNER):
    """Test that invalid syntax is handled properly."""
    header = fetch_header(test.client, role=role)
    rv = test.client.get(url, headers=header)
    test.assertEqual(rv.status_code, 400)


def check_invalid_semantics(test, url, check="none", role=ROLE_OWNER):
    """Test that invalid parameters and values are handled properly."""
    check_list = {
        "none": [""],
        "base": [],
        "boolean": ["=", "=-1", "=2", "=LoremIpsumDolorSitAmet"],
        "number": ["=", "=-1", "=0", "=LoremIpsumDolorSitAmet"],
        "integer": ["=", "=LoremIpsumDolorSitAmet"],
        "list": ["=LoremIpsumDolorSitAmet"],
    }
    header = fetch_header(test.client, role=role)
    for item in check_list[check]:
        rv = test.client.get("{}{}".format(url, item), headers=header)
        test.assertEqual(rv.status_code, 422)


def check_resource_missing(test, url, role=ROLE_OWNER):
    """Test that missing resources are handled properly."""
    header = fetch_header(test.client, role=role)
    rv = test.client.get(url, headers=header)
    test.assertEqual(rv.status_code, 404)


def check_requires_token(test, url, role=ROLE_OWNER):
    """Test that authorization is required."""
    rv = test.client.get(url)
    test.assertEqual(rv.status_code, 401)
    header = fetch_header(test.client, role=role)
    rv = test.client.get(url, headers=header)
    test.assertEqual(rv.status_code, 200)
    return rv.json


def check_conforms_to_schema(test, url, name, role=ROLE_OWNER):
    """Test that result set conforms to expected schema."""
    header = fetch_header(test.client, role=role)
    rv = test.client.get(url, headers=header)
    test.assertEqual(rv.status_code, 200)
    if isinstance(rv.json, type([])):
        for item in rv.json:
            validate(
                instance=item,
                schema=API_SCHEMA["definitions"][name],
                resolver=API_RESOLVER,
            )
    else:
        validate(
            instance=rv.json,
            schema=API_SCHEMA["definitions"][name],
            resolver=API_RESOLVER,
        )
    return rv.json


def check_totals(test, url, total, role=ROLE_OWNER):
    """Test that result set contains the expected number of objects."""
    header = fetch_header(test.client, role=role)
    rv = test.client.get(url, headers=header)
    test.assertEqual(rv.status_code, 200)
    test.assertIsInstance(rv.json, type([]))
    test.assertEqual(len(rv.json), total)
    count = rv.headers.pop("X-Total-Count")
    test.assertEqual(count, str(total))
    return rv.json


def check_strip_parameter(test, url, join="?", role=ROLE_OWNER):
    """Test that strip parameter produces expected result."""
    header = fetch_header(test.client, role=role)
    baseline = test.client.get(url, headers=header)
    rv = test.client.get("{}{}strip=1".format(url, join), headers=header)
    test.assertEqual(rv.status_code, 200)
    if isinstance(rv.json, type([])):
        for item in baseline.json:
            check_keys_stripped(test, item, rv.json[baseline.json.index(item)])
    else:
        check_keys_stripped(test, baseline.json, rv.json)
    return rv.json


def check_keys_parameter(test, url, keys, join="?", role=ROLE_OWNER):
    """Test that keys parameter produces expected result."""
    header = fetch_header(test.client, role=role)
    for key in keys:
        size = len(key.split(","))
        rv = test.client.get("{}{}keys={}".format(url, join, key), headers=header)
        test.assertEqual(rv.status_code, 200)
        if isinstance(rv.json, type([])):
            for item in rv.json:
                test.assertEqual(len(item), size)
                for part in key.split(","):
                    test.assertIn(part, item)
        else:
            test.assertEqual(len(rv.json), size)
            for part in key.split(","):
                test.assertIn(part, rv.json)
    return rv.json


def check_skipkeys_parameter(test, url, keys, join="?", role=ROLE_OWNER):
    """Test that skipkeys parameter produces expected result."""
    header = fetch_header(test.client, role=role)
    rv = test.client.get(url, headers=header)
    test.assertEqual(rv.status_code, 200)
    key_count = len(rv.json)
    if isinstance(rv.json, type([])):
        key_count = len(rv.json[0])
    for key in keys:
        size = key_count - len(key.split(","))
        rv = test.client.get("{}{}skipkeys={}".format(url, join, key), headers=header)
        test.assertEqual(rv.status_code, 200)
        if isinstance(rv.json, type([])):
            for item in rv.json:
                test.assertEqual(len(item), size)
                for part in key.split(","):
                    test.assertNotIn(part, item)
        else:
            test.assertEqual(len(rv.json), size)
            for part in key.split(","):
                test.assertNotIn(part, rv.json)
    return rv.json


def check_paging_parameters(test, url, size, join="?", role=ROLE_OWNER):
    """Test that page and pagesize parameters produce expected result."""
    header = fetch_header(test.client, role=role)
    rv = test.client.get(
        "{}{}page=1&pagesize={}".format(url, join, size), headers=header
    )
    test.assertEqual(rv.status_code, 200)
    test.assertIsInstance(rv.json, type([]))
    test.assertEqual(len(rv.json), size)
    first = rv.json[0]
    rv = test.client.get(
        "{}{}page=2&pagesize={}".format(url, join, size), headers=header
    )
    test.assertEqual(rv.status_code, 200)
    test.assertIsInstance(rv.json, type([]))
    test.assertEqual(len(rv.json), size)
    last = rv.json[-1]
    rv = test.client.get(
        "{}{}page=1&pagesize={}".format(url, join, size * 2), headers=header
    )
    test.assertEqual(rv.status_code, 200)
    test.assertIsInstance(rv.json, type([]))
    test.assertEqual(len(rv.json), size * 2)
    test.assertEqual(rv.json[0], first)
    test.assertEqual(rv.json[-1], last)
    return rv.json


def check_sort_parameter(
    test, url, sort_key, value_key=None, direction="+", join="?", role=ROLE_OWNER,
):
    """Test that sort parameter produces expected result."""
    header = fetch_header(test.client, role=role)
    item_key = sort_key
    if value_key is not None:
        item_key = value_key
    rv = test.client.get(
        "{}{}keys={}&sort={}{}".format(url, join, item_key, direction, sort_key),
        headers=header,
    )
    test.assertEqual(rv.status_code, 200)
    test.assertIsInstance(rv.json, type([]))
    if len(rv.json) > 1:
        index = 1
        if direction == "+":
            for item in rv.json[:-1]:
                test.assertLessEqual(item[item_key], rv.json[index][item_key])
                index = index + 1
        else:
            for item in rv.json[:-1]:
                test.assertGreaterEqual(item[item_key], rv.json[index][item_key])
                index = index + 1
    return rv.json


def check_single_extend_parameter(
    test, url, key, extended_key, join="?", reference=False, role=ROLE_OWNER,
):
    """Test that extend parameter produces expected result for a single key."""

    def validate_item(test, item, key, extended_key, reference):
        """Validate an extended item."""
        test.assertEqual(len(item["extended"]), 1)
        if isinstance(item[key], type([])):
            test.assertEqual(len(item[key]), len(item["extended"][extended_key]))
            for extended_item in item["extended"][extended_key]:
                if not reference:
                    test.assertIn(extended_item["handle"], item[key])
                else:
                    found = False
                    for reference_item in item[key]:
                        if reference_item["ref"] == extended_item["handle"]:
                            found = True
                            break
                    test.assertTrue(found)
        else:
            test.assertEqual(item["extended"][extended_key]["handle"], item[key])

    header = fetch_header(test.client, role=role)
    rv = test.client.get(
        "{}{}extend={}&keys={},extended".format(url, join, key, key), headers=header
    )
    test.assertEqual(rv.status_code, 200)
    if isinstance(rv.json, type([])):
        for item in rv.json:
            validate_item(test, item, key, extended_key, reference)
    else:
        validate_item(test, rv.json, key, extended_key, reference)
    return rv.json


def check_boolean_parameter(test, url, variable, join="?", role=ROLE_OWNER):
    """Test that variable boolean parameter produces expected result."""
    header = fetch_header(test.client, role=role)
    rv = test.client.get("{}{}{}=0".format(url, join, variable), headers=header)
    test.assertEqual(rv.status_code, 200)
    if isinstance(rv.json, type([])):
        for item in rv.json:
            test.assertNotIn(variable, item)
    else:
        test.assertNotIn(variable, rv.json)
    rv = test.client.get("{}{}{}=1".format(url, join, variable), headers=header)
    test.assertEqual(rv.status_code, 200)
    if isinstance(rv.json, type([])):
        for item in rv.json:
            test.assertIn(variable, item)
    else:
        test.assertIn(variable, rv.json)
    return rv.json


def check_filter_create_update_delete(test, base_url, test_url, namespace):
    """Test creation, application, update, and delete of a custom filter."""
    url = test_url + namespace
    payload = {
        "comment": "Test {} Filter".format(namespace.title()),
        "name": 123,
        "rules": [{"name": "HasTag", "values": ["ToDo"]}],
    }
    # check authorization required to post to endpoint
    rv = test.client.post(url, json=payload)
    test.assertEqual(rv.status_code, 401)

    # check response for invalid create due to bad schema
    header = fetch_header(test.client)
    rv = test.client.post(url, json=payload, headers=header)
    test.assertEqual(rv.status_code, 422)

    # check response for valid create
    payload["name"] = namespace.title() + "TestFilter"
    rv = test.client.post(url, json=payload, headers=header)
    test.assertEqual(rv.status_code, 201)

    # check response if filter already exists
    rv = test.client.post(url, json=payload, headers=header)
    test.assertEqual(rv.status_code, 422)

    # check can fetch the filter using query parm
    rv = check_success(test, url + "?filters=" + payload["name"])
    test.assertTrue(len(rv) == 1 and len(rv["filters"]) == 1)
    test.assertEqual(rv["filters"][0]["name"], payload["name"])

    # check can fetch the filter using path
    rv = check_success(test, url + "/" + payload["name"])
    test.assertEqual(rv["name"], payload["name"])

    # check response applying the filter
    check_success(test, base_url + "/" + namespace + "/?filter=" + payload["name"])

    # check response for put to bad endpoint
    header = fetch_header(test.client)
    rv = test.client.put(url + "bad", json=payload, headers=header)
    test.assertEqual(rv.status_code, 404)

    # check authorization required to put to endpoint
    rv = test.client.put(url, json=payload)
    test.assertEqual(rv.status_code, 401)

    # check response for update for filter that does not exist
    payload["name"] = payload["name"] + "Missing"
    rv = test.client.put(url, json=payload, headers=header)
    test.assertEqual(rv.status_code, 404)

    # check response for invalid update schema
    payload["name"] = namespace.title() + "TestFilter"
    payload["function"] = "junk"
    rv = test.client.put(url, json=payload, headers=header)
    test.assertEqual(rv.status_code, 422)

    # check response for valid update
    payload["function"] = "and"
    payload["comment"] = "Update works"
    rv = test.client.put(url, json=payload, headers=header)
    test.assertEqual(rv.status_code, 200)

    # check filter was actually updated
    rv = check_success(test, url + "?filters=" + payload["name"])
    test.assertEqual(rv["filters"][0]["comment"], "Update works")

    # check authorization required to issue delete
    rv = test.client.delete(url + "/" + payload["name"])
    test.assertEqual(rv.status_code, 401)

    # check authorized delete success
    header = fetch_header(test.client)
    rv = test.client.delete(url + "/" + payload["name"], headers=header)
    test.assertEqual(rv.status_code, 200)

    # check filter was actually deleted
    check_resource_missing(test, url + "?filters=" + payload["name"])
