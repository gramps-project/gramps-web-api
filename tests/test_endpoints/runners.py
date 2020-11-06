"""Test runner utility functions."""

from typing import Dict, List, Optional


def run_test_endpoint_gramps_id(test, endpoint: str, driver: Dict):
    """Test gramps_id parameter for a given endpoint."""
    # check 404 returned for non-existent object
    result = test.client.get(endpoint + "?gramps_id=does_not_exist")
    test.assertEqual(result.status_code, 404)
    # check only one record returned
    result = test.client.get(endpoint + "?gramps_id=" + driver["gramps_id"])
    test.assertEqual(len(result.json), 1)
    # check we have the expected record
    for key in driver:
        test.assertEqual(result.json[0][key], driver[key])


def run_test_endpoint_strip(test, endpoint: str):
    """Test strip parameter for a given endpoint."""
    # check 422 returned if passed argument
    result = test.client.get(endpoint + "?strip=1")
    test.assertEqual(result.status_code, 422)
    # check that keys for empty items are no longer in second object
    baseline = test.client.get(endpoint)
    result = test.client.get(endpoint + "?strip")
    if isinstance(result.json, type([])):
        for item in baseline.json:
            check_keys_stripped(test, item, result.json[baseline.json.index(item)])
    else:
        check_keys_stripped(test, baseline.json, result.json)


def check_keys_stripped(test, object1, object2):
    """Check keys for empty values in first object no longer exist in second."""
    for key in object1:
        if object1[key] in [[], {}, None]:
            test.assertNotIn(key, object2)
        else:
            if isinstance(object1[key], type({})):
                check_keys_stripped(test, object1[key], object2[key])
            if isinstance(object1[key], type([])):
                for item in object1:
                    if isinstance(item, (type([]), type({}))):
                        check_keys_stripped(test, item, object2[object1.index(item)])


def run_test_endpoint_keys(test, endpoint: str, keys: List[str]):
    """Test keys parameter for a given endpoint."""
    # check 422 returned if missing argument
    result = test.client.get(endpoint + "?keys")
    test.assertEqual(result.status_code, 422)
    # check results for the single key test that only key is present
    for key in keys:
        result = test.client.get(endpoint + "?keys=" + key)
        if isinstance(result.json, type([])):
            for item in result.json:
                test.assertEqual(len(item), 1)
                test.assertIn(key, item)
        else:
            test.assertEqual(len(result.json), 1)
            test.assertIn(key, result.json)
    # check results for the multi-key test that only keys are present
    result = test.client.get(endpoint + "?keys=" + ",".join(keys))
    if isinstance(result.json, type([])):
        for item in result.json:
            test.assertEqual(len(item), len(keys))
            for key in keys:
                test.assertIn(key, item)
    else:
        test.assertEqual(len(result.json), len(keys))
        for key in keys:
            test.assertIn(key, result.json)


def run_test_endpoint_skipkeys(test, endpoint: str, keys: List[str]):
    """Test skipkeys parameter for a given endpoint."""
    # check 422 returned if missing argument
    result = test.client.get(endpoint + "?skipkeys")
    test.assertEqual(result.status_code, 422)
    # get total key count for tests
    result = test.client.get(endpoint)
    if isinstance(result.json, type([])):
        key_count = len(result.json[0])
    else:
        key_count = len(result.json)
    # check results for the single key test that key was skipped
    size = key_count - 1
    for key in keys:
        result = test.client.get(endpoint + "?skipkeys=" + key)
        if isinstance(result.json, type([])):
            for item in result.json:
                test.assertEqual(len(item), size)
                test.assertNotIn(key, item)
        else:
            test.assertEqual(len(result.json), size)
            test.assertNotIn(key, result.json)
    # check results for the multi-key test that keys were skipped
    size = key_count - len(keys)
    result = test.client.get(endpoint + "?skipkeys=" + ",".join(keys))
    if isinstance(result.json, type([])):
        for item in result.json:
            test.assertEqual(len(item), size)
            for key in keys:
                test.assertNotIn(key, item)
    else:
        test.assertEqual(len(result.json), size)
        for key in keys:
            test.assertNotIn(key, result.json)


# The driver must be a list with an entry for all possible extended fields for the
# endpoint type. Each entry is a dict with arg, key, and type fields.  Example entries:
#
#     {"arg": "citation_list", "key": "citations", "type": List}
#     {"arg": "mother_handle", "key": "mother", "type": Dict}
#
# The driver_list is a optional list of Gramps IDs, if present will be used to query
# specific entries so the full result set from a list endpoint is not tested.


def run_test_endpoint_extend(
    test,
    endpoint: str,
    driver: List[Dict],
    driver_list: Optional[List[str]] = None,
):
    """Test extend parameter for a given endpoint."""
    driver_list = driver_list or []
    # check 422 returned if missing argument
    result = test.client.get(endpoint + "?extend")
    test.assertEqual(result.status_code, 422)
    # construct id list in event subset requested
    test_id_list = []
    expect_list = False
    if driver_list:
        expect_list = True
        for item in driver_list:
            test_id_list.append("&gramps_id=" + item)
    else:
        test_id_list = [""]
    # check only the requested item is present in the result set
    for test_id in test_id_list:
        for test_case in driver:
            result = test.client.get(endpoint + "?extend=" + test_case["arg"] + test_id)
            if expect_list:
                test.assertEqual(len(result.json[0]["extended"]), 1)
                test.assertIsInstance(
                    result.json[0]["extended"][test_case["key"]], test_case["type"]
                )
            else:
                test.assertEqual(len(result.json["extended"]), 1)
                test.assertIsInstance(
                    result.json["extended"][test_case["key"]], test_case["type"]
                )
    # check all expected items are present in the result set
    for test_id in test_id_list:
        result = test.client.get(endpoint + "?extend=all" + test_id)
        if expect_list:
            for item in result.json:
                test.assertEqual(len(item["extended"]), len(driver))
                for test_case in driver:
                    test.assertIsInstance(
                        item["extended"][test_case["key"]], test_case["type"]
                    )
        else:
            test.assertEqual(len(result.json["extended"]), len(driver))
            for test_case in driver:
                test.assertIsInstance(
                    result.json["extended"][test_case["key"]], test_case["type"]
                )
    # check multiple tags work as expected by using two together
    if len(driver_list) > 1:
        for test_id in test_id_list:
            result = test.client.get(
                endpoint
                + "?extend="
                + driver[0]["arg"]
                + ","
                + driver[0]["arg"]
                + test_id
            )
            if expect_list:
                test.assertEqual(len(result.json[0]["extended"]), 2)
                test.assertIsInstance(
                    result.json[0]["extended"][driver[0]["key"]],
                    driver[0]["type"],
                )
                test.assertIsInstance(
                    result.json[0]["extended"][driver[1]["key"]],
                    driver[1]["type"],
                )
            else:
                test.assertEqual(len(result.json["extended"]), 2)
                test.assertIsInstance(
                    result.json["extended"][driver[0]["key"]], driver[0]["type"]
                )
                test.assertIsInstance(
                    result.json["extended"][driver[1]["key"]], driver[1]["type"]
                )


def run_test_endpoint_rules(test, endpoint: str, driver: Dict):
    """Test rules parameter for a given endpoint."""
    # check 400 returned if passed improperly formatted argument
    for rules in driver[400]:
        result = test.client.get(endpoint + "?rules=" + rules)
        test.assertEqual(result.status_code, 400)
    # check 422 returned if passed properly formatted argument with invalid schema
    for rules in driver[422]:
        result = test.client.get(endpoint + "?rules=" + rules)
        test.assertEqual(result.status_code, 422)
    # check 404 returned if passed proper construct but with non-existent rule
    for rules in driver[404]:
        result = test.client.get(endpoint + "?rules=" + rules)
        test.assertEqual(result.status_code, 404)
    # check 200 returned if rules filter constructed and executed properly
    for rules in driver[200]:
        result = test.client.get(endpoint + "?rules=" + rules)
        test.assertEqual(result.status_code, 200)


def run_test_filters_endpoint_namespace(test, namespace: str, payload: Dict):
    """Test creation, application, update, and delete of a custom filter."""
    # check 422 returned if missing rules parm argument
    rule = payload["rules"][0]["name"]
    result = test.client.get("/api/filters/" + namespace + "?rules")
    test.assertEqual(result.status_code, 422)
    # check 404 returned if rule does not exist
    result = test.client.get("/api/filters/" + namespace + "?rules=IsSomeoneSomewhere")
    test.assertEqual(result.status_code, 404)
    # check single rule returned okay
    result = test.client.get("/api/filters/" + namespace + "?rules=" + rule)
    test.assertEqual(len(result.json["rules"]), 1)
    test.assertEqual(result.json["rules"][0]["rule"], rule)
    # check response for invalid create custom filter schema
    payload["name"] = 123
    result = test.client.post("/api/filters/" + namespace, json=payload)
    test.assertEqual(result.status_code, 422)
    # check response for post to bad endpoint
    filter_name = namespace.title() + "TestFilter"
    payload["name"] = filter_name
    result = test.client.post("/api/filters/junk", json=payload)
    test.assertEqual(result.status_code, 404)
    # check response for valid create
    result = test.client.post("/api/filters/" + namespace, json=payload)
    test.assertEqual(result.status_code, 201)
    # check response if filter already exists
    result = test.client.post("/api/filters/" + namespace, json=payload)
    test.assertEqual(result.status_code, 422)
    # check can fetch the filter
    result = test.client.get("/api/filters/" + namespace + "?filters=" + filter_name)
    test.assertEqual(result.status_code, 200)
    test.assertTrue(len(result.json) == 1 and len(result.json["filters"]) == 1)
    test.assertEqual(result.json["filters"][0]["name"], filter_name)
    # check response if fetching filter that does not exist
    result = test.client.get(
        "/api/filters/" + namespace + "?filters=" + filter_name + "Missing"
    )
    test.assertEqual(result.status_code, 404)
    # check response applying filter that does not exist
    result = test.client.get(
        "/api/" + namespace + "/?filter=" + filter_name + "Missing"
    )
    test.assertEqual(result.status_code, 404)
    # check response applying the filter
    result = test.client.get("/api/" + namespace + "/?filter=" + filter_name)
    test.assertEqual(result.status_code, 200)
    test.assertGreater(len(result.json), 0)
    # check response for put to bad endpoint
    result = test.client.put("/api/filters/" + namespace + "bad", json=payload)
    test.assertEqual(result.status_code, 404)
    # check response for update for filter that does not exist
    payload["name"] = filter_name + "Missing"
    result = test.client.put("/api/filters/" + namespace, json=payload)
    test.assertEqual(result.status_code, 404)
    # check response for invalid update schema
    payload["name"] = filter_name
    payload["function"] = "junk"
    result = test.client.put("/api/filters/" + namespace, json=payload)
    test.assertEqual(result.status_code, 422)
    # check response for valid update
    payload["function"] = "and"
    payload["comment"] = "Update works"
    result = test.client.put("/api/filters/" + namespace, json=payload)
    test.assertEqual(result.status_code, 200)
    # check filter was actually updated
    result = test.client.get("/api/filters/" + namespace + "?filters=" + filter_name)
    test.assertEqual(result.status_code, 200)
    test.assertEqual(result.json["filters"][0]["comment"], "Update works")
    # check delete success
    result = test.client.delete("/api/filters/" + namespace + "/" + filter_name)
    test.assertEqual(result.status_code, 200)
    # check filter was actually deleted
    result = test.client.get("/api/filters/" + namespace + "?filters=" + filter_name)
    test.assertEqual(result.status_code, 404)
