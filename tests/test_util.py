import logging
from unittest.mock import MagicMock, patch

import pytest
from gramps.gen.errors import HandleError
from gramps.gen.lib import Citation, EventType
from gramps.gen.lib.json_utils import data_to_object

from gramps_webapi.api import util
from gramps_webapi.api.resources.util import (
    fix_object_dict,
    get_citation_profile_for_object,
)
from gramps_webapi.api.util import send_email
from gramps_webapi.const import PRIMARY_GRAMPS_OBJECTS


def test_fix_object_dict_localized_event_type():
    """Test fix_object_dict with localized (German) event type string.

    This tests the fix for localized type strings (e.g. German "Geburt").
    Since _S2IMAP is built at module import time based on system locale,
    we need to manually add the German string to simulate German locale.
    """
    event_dict = {"_class": "Event", "type": "Geburt"}
    # Simulate German locale by adding German string to _S2IMAP
    # _S2IMAP is built at import time; add German string for this test
    had_geburt = "Geburt" in EventType._S2IMAP
    old_geburt_value = EventType._S2IMAP.get("Geburt")
    EventType._S2IMAP["Geburt"] = 12
    try:
        result = fix_object_dict(event_dict, "Event")
        assert result["type"]["value"] == 12
    finally:
        if had_geburt:
            EventType._S2IMAP["Geburt"] = old_geburt_value
        else:
            # Only remove the key if we introduced it
            EventType._S2IMAP.pop("Geburt", None)


def test_fix_object_dict_xml_event_type():
    """Test fix_object_dict with English XML event type string."""
    event_dict = {"_class": "Event", "type": "Birth"}
    result = fix_object_dict(event_dict, "Event")
    assert result["type"]["value"] == 12


def test_fix_object_dict_custom_event_type():
    """Test fix_object_dict with custom event type string."""
    event_dict = {"_class": "Event", "type": "MyCustomEvent"}
    result = fix_object_dict(event_dict, "Event")
    assert result["type"]["value"] == 0


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
    with patch("gramps_webapi.api.util.current_app", MagicMock()):
        send_email("Subject", "Body", ["test@example.com"])
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
    with patch("gramps_webapi.api.util.current_app", MagicMock()):
        send_email("Subject", "Body", ["test@example.com"])
    mock_smtp.assert_called_once()
    mock_smtp_instance.starttls.assert_called_once()
    mock_smtp_ssl.assert_not_called()


def test_recalc_date_sortvals_fixes_stale_sortval():
    """gramps-web-api#869: a client-supplied stale/zero sortval must be recomputed."""
    from gramps.gen.lib import Date
    from gramps.gen.lib.json_utils import object_to_dict

    from gramps_webapi.api.util import gramps_object_from_dict, recalc_date_sortvals

    date = Date()
    date.set_yr_mon_day(1922, 5, 3)
    correct = date.sortval
    assert correct  # 2423178, computed by gramps

    # an Event whose embedded Date arrives with a corrupted sortval
    event = {
        "_class": "Event",
        "type": {"_class": "EventType", "value": 12, "string": "Birth"},
        "date": object_to_dict(date),
    }
    event["date"]["sortval"] = 0
    recalc_date_sortvals(event)
    assert event["date"]["sortval"] == correct

    # and end-to-end through the deserializer used by the write endpoints
    event["date"]["sortval"] = 1
    obj = gramps_object_from_dict(event)
    assert obj.get_date_object().sortval == correct


def test_recalc_date_sortvals_year_only():
    """Year-only dates (no month/day) also get a correct sortval."""
    from gramps.gen.lib import Date
    from gramps.gen.lib.json_utils import object_to_dict

    from gramps_webapi.api.util import recalc_date_sortvals

    date = Date()
    date.set_yr_mon_day(1827, 0, 0)
    correct = date.sortval
    date_dict = object_to_dict(date)
    date_dict["sortval"] = 0
    recalc_date_sortvals({"_class": "Event", "date": date_dict})
    assert date_dict["sortval"] == correct


def test_validate_object_dict_does_not_mutate_shared_schema():
    """validate_object_dict() must not mutate a shared/cached get_schema() result.

    Gramps core may cache Person.get_schema() and return the same object to
    every caller. The gender-max patch here (for Person.OTHER, added in
    Gramps 5.2) previously mutated that returned schema in place, which
    would corrupt it for every other caller of get_schema() once Gramps
    starts sharing/caching it, or raise outright if the shared object is
    made read-only.
    """
    from gramps.gen.lib import Person

    from gramps_webapi.api.resources.util import validate_object_dict

    # Simulate a schema whose declared gender maximum hasn't caught up with
    # Person.OTHER yet -- the exact case this patch exists to handle.
    shared_schema = {
        "type": "object",
        "properties": {
            "_class": {"enum": ["Person"]},
            "gender": {"type": "integer", "maximum": Person.OTHER - 1},
        },
    }

    with patch.object(Person, "get_schema", return_value=shared_schema):
        obj_dict = {"_class": "Person", "gender": Person.OTHER}
        validate_object_dict(obj_dict)

        # The object returned by get_schema() is shared across every call;
        # it must come back untouched.
        assert shared_schema["properties"]["gender"]["maximum"] == Person.OTHER - 1

        # And a second call must still succeed -- it can't rely on a
        # mutation left behind by the first call.
        validate_object_dict(obj_dict)


def test_validate_object_dict_error_names_the_offending_field():
    """A schema violation must say which field was wrong, not just that one was."""
    from flask import Flask

    from gramps_webapi.api.resources.util import validate_object_dict

    with Flask(__name__).app_context():
        with pytest.raises(ValueError) as excinfo:
            validate_object_dict({"_class": "Person", "citation_list": "not-a-list"})

    assert "citation_list" in str(excinfo.value)


@pytest.mark.parametrize("class_name", ["__path__", "person", "__spec__", 42])
def test_validate_object_dict_rejects_non_class_attributes(class_name):
    """`_class` is client-controlled on POST /objects/.

    Names like "person" or "__path__" resolve as gramps.gen.lib attributes but
    have no get_schema(), which used to surface as an uncaught AttributeError
    -- a 500 reported to Sentry -- rather than a 400.
    """
    from gramps_webapi.api.resources.util import validate_object_dict

    with pytest.raises(ValueError):
        validate_object_dict({"_class": class_name})


@pytest.mark.parametrize(
    "obj_dict,expected",
    [
        # the payload the frontend produces when a media object form is saved
        # with nothing selected -- see gramps-web-api#479
        ({"_class": "Person", "media_list": [{}]}, "MediaRef"),
        (
            {"_class": "Person", "media_list": [{"_class": "MediaRef", "ref": ""}]},
            "MediaRef",
        ),
        ({"_class": "Person", "event_ref_list": [{}]}, "EventRef"),
        ({"_class": "Person", "person_ref_list": [{}]}, "PersonRef"),
        ({"_class": "Family", "child_ref_list": [{}]}, "ChildRef"),
        ({"_class": "Place", "placeref_list": [{}]}, "PlaceRef"),
        ({"_class": "Source", "reporef_list": [{}]}, "RepoRef"),
    ],
)
def test_validate_object_dict_rejects_reference_without_target(obj_dict, expected):
    """A reference without a target is stored as `ref = None`.

    Gramps' check tool cannot see such a reference and the Gramps XML export
    crashes on it, so it has to be rejected on the way in.
    """
    from flask import Flask

    from gramps_webapi.api.resources.util import fix_object_dict, validate_object_dict

    with Flask(__name__).app_context():
        with pytest.raises(ValueError) as excinfo:
            validate_object_dict(fix_object_dict(obj_dict))

    assert expected in str(excinfo.value)


def test_validate_object_dict_accepts_reference_with_target():
    """A reference that names a handle must still pass."""
    from flask import Flask

    from gramps_webapi.api.resources.util import fix_object_dict, validate_object_dict

    obj_dict = {
        "_class": "Person",
        "media_list": [{"_class": "MediaRef", "ref": "abcd1234"}],
    }
    with Flask(__name__).app_context():
        validate_object_dict(fix_object_dict(obj_dict))


@pytest.mark.parametrize(
    "date_dict",
    [
        # a range/span whose stop half is missing -- Date.get_stop_date() slices
        # dateval[4:8] and returns an empty tuple, which the date displayer
        # then indexes into
        {"_class": "Date", "modifier": 4, "dateval": [1, 1, 1900, False]},
        {"_class": "Date", "modifier": 5, "dateval": [1, 1, 1900, False]},
        # no dateval at all: completion fills in the empty four-value date,
        # which is just as short
        {"_class": "Date", "modifier": 4},
        # a simple date that cannot even fill its start half
        {"_class": "Date", "modifier": 0, "dateval": [1, 1]},
        {"_class": "Date", "modifier": 3, "dateval": []},
    ],
)
def test_validate_object_dict_rejects_date_too_short_for_modifier(date_dict):
    """A date with fewer values than its modifier needs must not be stored.

    Gramps' own Date.set() enforces this, but data_to_object() bypasses it and
    the Gramps JSON schema puts no length constraint on dateval, so such a date
    is persisted and then raises IndexError on every attempt to display it.
    """
    from flask import Flask

    from gramps_webapi.api.resources.util import fix_object_dict, validate_object_dict

    obj_dict = {"_class": "Event", "date": date_dict}
    with Flask(__name__).app_context():
        with pytest.raises(ValueError) as excinfo:
            validate_object_dict(fix_object_dict(obj_dict))

    assert "dateval" in str(excinfo.value)
    assert "$.date" in str(excinfo.value)


@pytest.mark.parametrize(
    "date_dict",
    [
        {"_class": "Date", "modifier": 0, "dateval": [1, 1, 1900, False]},
        {
            "_class": "Date",
            "modifier": 4,
            "dateval": [1, 1, 1900, False, 2, 2, 1950, False],
        },
        # text-only dates do not read dateval
        {"_class": "Date", "modifier": 6, "dateval": [], "text": "sometime"},
        # a partial date dict must keep working
        {"_class": "Date"},
    ],
)
def test_validate_object_dict_accepts_displayable_date(date_dict):
    """Every date Gramps itself can display must still pass."""
    from flask import Flask
    from gramps.gen.const import GRAMPS_LOCALE as glocale

    from gramps_webapi.api.resources.util import fix_object_dict, validate_object_dict
    from gramps_webapi.api.util import gramps_object_from_dict

    obj_dict = fix_object_dict({"_class": "Event", "date": date_dict})
    with Flask(__name__).app_context():
        validate_object_dict(obj_dict)

    # the point of the check: whatever survives it can be displayed
    obj = gramps_object_from_dict(obj_dict)
    glocale.date_displayer.display(obj.date)


@pytest.mark.parametrize("modifier", [4, 5])
def test_display_date_survives_a_date_gramps_cannot_format(modifier, caplog):
    """A date already stored with too few values must not raise.

    Validation rejects these on the way in, but trees written before that check
    existed still hold them, and one such date must not turn a whole profile
    response into a 500.
    """
    from gramps.gen.lib import Date

    from gramps_webapi.api.resources.util import display_date

    date = Date()
    date.set_modifier(modifier)
    date.dateval = (1, 1, 1900, False)

    with caplog.at_level(logging.WARNING):
        assert display_date(date) == ""

    # the log names the shape of the date, never its values
    assert "Cannot display date" in caplog.text
    assert "1900" not in caplog.text


def test_display_date_falls_back_to_the_date_text():
    """A broken date that carries verbatim user input shows that input."""
    from gramps.gen.lib import Date

    from gramps_webapi.api.resources.util import display_date

    date = Date()
    date.set_modifier(Date.MOD_SPAN)
    date.dateval = (1, 1, 1900, False)
    date.text = "from about 1900"

    assert display_date(date) == "from about 1900"


def test_display_date_formats_a_normal_date():
    """The fallback must not change what a valid date looks like."""
    from gramps.gen.const import GRAMPS_LOCALE as glocale
    from gramps.gen.lib import Date

    from gramps_webapi.api.resources.util import display_date

    date = Date()
    date.set_yr_mon_day(1900, 1, 1)

    assert display_date(date) == glocale.date_displayer.display(date)


def test_display_date_handles_a_missing_date():
    """`probably_alive_range` returns None when it cannot infer a date."""
    from gramps_webapi.api.resources.util import display_date

    assert display_date(None) == ""


def test_display_date_does_not_swallow_unexpected_errors():
    """Only malformed stored dates are tolerated; real bugs must surface.

    A misconfigured locale or a programming error would otherwise be converted
    into a blank date and go unnoticed in production.
    """
    from gramps.gen.lib import Date

    from gramps_webapi.api.resources.util import display_date

    locale = MagicMock()
    locale.date_displayer.display.side_effect = RuntimeError("locale is broken")

    with pytest.raises(RuntimeError):
        display_date(Date(), locale)


def test_citation_profile_survives_a_broken_source_reference():
    """A citation whose source is missing is still a valid citation."""
    db_handle = MagicMock()
    db_handle.get_source_from_handle.side_effect = HandleError(
        "Handle nonexistent not found"
    )
    citation = Citation()
    citation.set_handle("c0001")
    citation.set_gramps_id("C0001")
    citation.set_page("p. 42")
    citation.set_reference_handle("nonexistent")

    profile = get_citation_profile_for_object(db_handle, citation, [])

    assert profile["source"] == {}
    assert profile["gramps_id"] == "C0001"
    assert profile["page"] == "p. 42"
