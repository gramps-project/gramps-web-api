import pytest
from gramps.gen.lib.json_utils import data_to_object

from gramps_webapi.api import util
from gramps_webapi.const import PRIMARY_GRAMPS_OBJECTS


def _test_complete_gramps_object_dict(obj_dict):
    util.complete_gramps_object_dict(obj_dict)
    # this will raise an exception if the object dict is not valid
    data_to_object(obj_dict)


def test_complete_gramps_object_dict_empty():
    """Test with empty dictionaries for each primary object"""
    for class_name in PRIMARY_GRAMPS_OBJECTS:
        if class_name == "Family":
            continue
        obj_dict = {"_class": class_name}
        try:
            _test_complete_gramps_object_dict(obj_dict)
        except:
            pytest.fail(f"Failed to complete {class_name} object dict")
            raise


def test_complete_gramps_object_dict_nested():
    """Test with nested objects that need completion."""
    # Test a Person with incomplete Name object
    person_dict = {
        "_class": "Person",
        "gender": 0,
        "primary_name": {"_class": "Name", "first_name": "John"},
    }
    _test_complete_gramps_object_dict(person_dict)

    # Test an Event with incomplete Place reference
    event_dict = {"_class": "Event", "place": {"_class": "PlaceRef", "ref": "abcd1234"}}
    _test_complete_gramps_object_dict(event_dict)


def test_complete_gramps_object_dict_lists():
    """Test with objects containing lists of other objects."""
    # Test Person with attribute list
    person_dict = {
        "_class": "Person",
        "attribute_list": [
            {"_class": "Attribute", "type": "Birth", "value": "Hospital"}
        ],
    }
    _test_complete_gramps_object_dict(person_dict)


def test_complete_gramps_object_dict_secondary_objects():
    """Test with various secondary objects that aren't in PRIMARY_GRAMPS_OBJECTS."""
    secondary_objects = [
        "Date",
        "Address",
        "Location",
        "Attribute",
        "Surname",
        "Name",
        "PlaceRef",
        "MediaRef",
        "EventRef",
        "Url",
    ]

    for class_name in secondary_objects:
        obj_dict = {"_class": class_name}
        try:
            _test_complete_gramps_object_dict(obj_dict)
        except:
            pytest.fail(f"Failed to complete {class_name} object dict")
            raise


def test_complete_gramps_object_dict_with_data():
    """Test with dictionaries containing partial data."""
    obj_dict = {
        "_class": "Person",
        "gender": 1,  # Female
        "primary_name": {
            "_class": "Name",
            "first_name": "Jane",
            "surname_list": [{"_class": "Surname", "surname": "Doe"}],
        },
    }
    _test_complete_gramps_object_dict(obj_dict)

    # The dictionary should now be complete and can be converted to a Person object
    assert obj_dict["_class"] == "Person"
    assert obj_dict["gender"] == 1
    assert "attribute_list" in obj_dict
    assert "address_list" in obj_dict
    assert "event_ref_list" in obj_dict


def test_complete_gramps_object_dict_non_gramps_dict():
    """Test with dictionaries that are not Gramps objects."""
    # Dictionary without _class should be returned unchanged
    obj_dict = {"name": "Test", "value": 123}
    result = util.complete_gramps_object_dict(obj_dict.copy())
    assert result == obj_dict
