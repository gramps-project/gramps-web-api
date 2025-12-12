import pytest
from gramps.gen.lib.json_utils import data_to_object

from gramps_webapi.api import util
from gramps_webapi.const import PRIMARY_GRAMPS_OBJECTS

from unittest.mock import MagicMock, patch
from gramps_webapi.api.util import send_email

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


@pytest.fixture
def mock_get_config():
    """Mock get_config function."""
    config = {
        "EMAIL_HOST": "smtp.example.com",
        "EMAIL_PORT": "587",
        "EMAIL_HOST_USER": "user@example.com",
        "EMAIL_HOST_PASSWORD": "password",
        "DEFAULT_FROM_EMAIL": "noreply@example.com",
        "EMAIL_USE_SSL": None,
        "EMAIL_USE_STARTTLS": None,
        "EMAIL_USE_TLS": True,
    }

    def get_config(key):
        return config.get(key)

    with patch("gramps_webapi.api.util.get_config", side_effect=get_config):
        yield config


@patch("gramps_webapi.api.util.smtplib.SMTP_SSL")
@patch("gramps_webapi.api.util.smtplib.SMTP")
def test_send_email_uses_smtp_ssl(mock_smtp, mock_smtp_ssl, mock_get_config):
    """Test that EMAIL_USE_SSL=true uses SMTP_SSL."""
    mock_get_config["EMAIL_USE_SSL"] = True
    mock_get_config["EMAIL_PORT"] = "465"
    mock_smtp_ssl.return_value = MagicMock()
    with patch("gramps_webapi.api.util.current_app", MagicMock()):
        send_email("Subject", "Body", ["test@example.com"])
    mock_smtp_ssl.assert_called_once()
    mock_smtp.assert_not_called()


@patch("gramps_webapi.api.util.smtplib.SMTP_SSL")
@patch("gramps_webapi.api.util.smtplib.SMTP")
def test_send_email_uses_starttls(mock_smtp, mock_smtp_ssl, mock_get_config):
    """Test that EMAIL_USE_STARTTLS=true uses SMTP with starttls."""
    mock_get_config["EMAIL_USE_STARTTLS"] = True
    mock_get_config["EMAIL_PORT"] = "587"
    mock_smtp_instance = MagicMock()
    mock_smtp.return_value = mock_smtp_instance
    with patch("gramps_webapi.api.util.current_app", MagicMock()):
        send_email("Subject", "Body", ["test@example.com"])
    mock_smtp.assert_called_once()
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_ssl.assert_not_called()


@patch("gramps_webapi.api.util.smtplib.SMTP_SSL")
@patch("gramps_webapi.api.util.smtplib.SMTP")
def test_send_email_uses_plain_smtp(mock_smtp, mock_smtp_ssl, mock_get_config):
    """Test that neither SSL nor STARTTLS uses plain SMTP."""
    mock_get_config["EMAIL_USE_SSL"] = False
    mock_get_config["EMAIL_USE_STARTTLS"] = False
    mock_get_config["EMAIL_PORT"] = "25"
    mock_smtp_instance = MagicMock()
    mock_smtp.return_value = mock_smtp_instance
    with patch("gramps_webapi.api.util.current_app", MagicMock()):
        send_email("Subject", "Body", ["test@example.com"])
    mock_smtp.assert_called_once()
    mock_smtp_instance.starttls.assert_not_called()
    mock_smtp_ssl.assert_not_called()


@patch("gramps_webapi.api.util.smtplib.SMTP_SSL")
@patch("gramps_webapi.api.util.smtplib.SMTP")
def test_send_email_legacy_use_tls_true(mock_smtp, mock_smtp_ssl, mock_get_config):
    """Test legacy EMAIL_USE_TLS=true uses SMTP_SSL."""
    mock_get_config["EMAIL_USE_TLS"] = True
    mock_get_config["EMAIL_PORT"] = "465"
    mock_smtp_ssl.return_value = MagicMock()
    mock_app = MagicMock()
    with patch("gramps_webapi.api.util.current_app", mock_app):
        send_email("Subject", "Body", ["test@example.com"])
        mock_app.logger.warning.assert_called_once()
    mock_smtp_ssl.assert_called_once()
    mock_smtp.assert_not_called()


@patch("gramps_webapi.api.util.smtplib.SMTP_SSL")
@patch("gramps_webapi.api.util.smtplib.SMTP")
def test_send_email_legacy_use_tls_false(mock_smtp, mock_smtp_ssl, mock_get_config):
    """Test legacy EMAIL_USE_TLS=false uses STARTTLS on port 587."""
    mock_get_config["EMAIL_USE_TLS"] = False
    mock_get_config["EMAIL_PORT"] = "587"
    mock_smtp_instance = MagicMock()
    mock_smtp.return_value = mock_smtp_instance
    with patch("gramps_webapi.api.util.current_app", MagicMock()):
        send_email("Subject", "Body", ["test@example.com"])
    mock_smtp.assert_called_once()
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_ssl.assert_not_called()


@patch("gramps_webapi.api.util.smtplib.SMTP_SSL")
@patch("gramps_webapi.api.util.smtplib.SMTP")
def test_send_email_ssl_false_starttls_true(mock_smtp, mock_smtp_ssl, mock_get_config):
    """Test that EMAIL_USE_SSL=false doesn't prevent EMAIL_USE_STARTTLS=true from working."""
    mock_get_config["EMAIL_USE_SSL"] = False
    mock_get_config["EMAIL_USE_STARTTLS"] = True
    mock_get_config["EMAIL_PORT"] = "587"
    mock_smtp_instance = MagicMock()
    mock_smtp.return_value = mock_smtp_instance
    mock_app = MagicMock()
    with patch("gramps_webapi.api.util.current_app", mock_app):
        send_email("Subject", "Body", ["test@example.com"])
        mock_app.logger.warning.assert_not_called()
    mock_smtp.assert_called_once()
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_ssl.assert_not_called()


@patch("gramps_webapi.api.util.smtplib.SMTP_SSL")
@patch("gramps_webapi.api.util.smtplib.SMTP")
def test_send_email_legacy_use_tls_false_deprecation_warning(mock_smtp, mock_smtp_ssl, mock_get_config):
    """Test that legacy EMAIL_USE_TLS=false logs deprecation warning."""
    mock_get_config["EMAIL_USE_TLS"] = False
    mock_get_config["EMAIL_PORT"] = "587"
    mock_smtp_instance = MagicMock()
    mock_smtp.return_value = mock_smtp_instance
    mock_app = MagicMock()
    with patch("gramps_webapi.api.util.current_app", mock_app):
        send_email("Subject", "Body", ["test@example.com"])
        mock_app.logger.warning.assert_called_once()
        warning_msg = mock_app.logger.warning.call_args[0][0]
        assert "deprecated" in warning_msg.lower()
    mock_smtp.assert_called_once()
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_ssl.assert_not_called()
