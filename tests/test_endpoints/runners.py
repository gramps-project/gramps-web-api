"""Test runner utility functions."""

from typing import Dict, List, Optional


def run_test_endpoint_gramps_id(client, endpoint: str, driver: Dict):
    """Test gramps_id parameter for a given endpoint."""
    # check 404 returned for non-existent object
    rv = client.get(endpoint + "?gramps_id=does_not_exist")
    assert rv.status_code == 404
    # check only one record returned
    rv = client.get(endpoint + "?gramps_id=" + driver["gramps_id"])
    assert len(rv.json) == 1
    # check we have the expected record
    for key in driver:
        assert rv.json[0][key] == driver[key]


def run_test_endpoint_strip(client, endpoint: str):
    """Test strip parameter for a given endpoint."""
    # check 422 returned if passed argument
    rv = client.get(endpoint + "?strip=1")
    assert rv.status_code == 422
    # check that keys for empty items are no longer in second object
    bv = client.get(endpoint)
    rv = client.get(endpoint + "?strip")
    if isinstance(rv.json, List):
        for item in bv.json:
            check_keys_stripped(item, rv.json[bv.json.index(item)])
    else:
        check_keys_stripped(bv.json, rv.json)


def check_keys_stripped(object1, object2):
    """Check keys for empty values in first object no longer exist in second."""
    for key in object1:
        if object1[key] in [[], {}, None]:
            assert key not in object2
        else:
            if isinstance(object1[key], Dict):
                check_keys_stripped(object1[key], object2[key])
            if isinstance(object1[key], List):
                for item in object1:
                    if isinstance(item, List) or isinstance(item, Dict):
                        check_keys_stripped(item, object2[object1.index(item)])


def run_test_endpoint_keys(client, endpoint: str, keys: List[str]):
    """Test keys parameter for a given endpoint."""
    # check 422 returned if missing argument
    rv = client.get(endpoint + "?keys")
    assert rv.status_code == 422
    # check results for the single key test that only key is present
    for key in keys:
        rv = client.get(endpoint + "?keys=" + key)
        if isinstance(rv.json, List):
            for item in rv.json:
                assert len(item) == 1
                assert key in item
        else:
            assert len(rv.json) == 1
            assert key in rv.json
    # check results for the multi-key test that only keys are present
    rv = client.get(endpoint + "?keys=" + ",".join(keys))
    if isinstance(rv.json, List):
        for item in rv.json:
            assert len(item) == len(keys)
            for key in keys:
                assert key in item
    else:
        assert len(rv.json) == len(keys)
        for key in keys:
            assert key in rv.json


def run_test_endpoint_skipkeys(client, endpoint: str, keys: List[str]):
    """Test skipkeys parameter for a given endpoint."""
    # check 422 returned if missing argument
    rv = client.get(endpoint + "?skipkeys")
    assert rv.status_code == 422
    # get total key count for tests
    rv = client.get(endpoint)
    if isinstance(rv.json, List):
        key_count = len(rv.json[0])
    else:
        key_count = len(rv.json)
    # check results for the single key test that key was skipped
    size = key_count - 1
    for key in keys:
        rv = client.get(endpoint + "?skipkeys=" + key)
        if isinstance(rv.json, List):
            for item in rv.json:
                assert len(item) == size
                assert key not in item
        else:
            assert len(rv.json) == size
            assert key not in rv.json
    # check results for the multi-key test that keys were skipped
    size = key_count - len(keys)
    rv = client.get(endpoint + "?skipkeys=" + ",".join(keys))
    if isinstance(rv.json, List):
        for item in rv.json:
            assert len(item) == size
            for key in keys:
                assert key not in item
    else:
        assert len(rv.json) == size
        for key in keys:
            assert key not in rv.json


# The driver must be a list with an entry for all possible extended fields for the
# endpoint type. Each entry is a dict with arg, key, and type fields.  Example entries:
#
#     {"arg": "citation_list", "key": "citations", "type": List}
#     {"arg": "mother_handle", "key": "mother", "type": Dict}
#
# The driver_list is a optional list of Gramps IDs, if present will be used to query
# specific entries so the full result set from a list endpoint is not tested.


def run_test_endpoint_extend(
    client, endpoint: str, driver: List[Dict], driver_list: Optional[List[str]] = None
):
    """Test extend parameter for a given endpoint."""
    driver_list = driver_list or []
    # check 422 returned if missing argument
    rv = client.get(endpoint + "?extend")
    assert rv.status_code == 422
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
        for test in driver:
            rv = client.get(endpoint + "?extend=" + test["arg"] + test_id)
            if expect_list:
                assert len(rv.json[0]["extended"]) == 1
                assert isinstance(rv.json[0]["extended"][test["key"]], test["type"])
            else:
                assert len(rv.json["extended"]) == 1
                assert isinstance(rv.json["extended"][test["key"]], test["type"])
    # check all expected items are present in the result set
    for test_id in test_id_list:
        rv = client.get(endpoint + "?extend=all" + test_id)
        if expect_list:
            for item in rv.json:
                assert len(item["extended"]) == len(driver)
                for test in driver:
                    assert isinstance(item["extended"][test["key"]], test["type"])
        else:
            assert len(rv.json["extended"]) == len(driver)
            for test in driver:
                assert isinstance(rv.json["extended"][test["key"]], test["type"])
    # check multiple tags work as expected by using two together
    if len(driver_list) > 1:
        for test_id in test_id_list:
            rv = client.get(
                endpoint
                + "?extend="
                + driver[0]["arg"]
                + ","
                + driver[0]["arg"]
                + test_id
            )
            if expect_list:
                assert len(rv.json[0]["extended"]) == 2
                assert isinstance(
                    rv.json[0]["extended"][driver[0]["key"]],
                    driver[0]["type"],
                )
                assert isinstance(
                    rv.json[0]["extended"][driver[1]["key"]],
                    driver[1]["type"],
                )
            else:
                assert len(rv.json["extended"]) == 2
                assert isinstance(
                    rv.json["extended"][driver[0]["key"]], driver[0]["type"]
                )
                assert isinstance(
                    rv.json["extended"][driver[1]["key"]], driver[1]["type"]
                )
