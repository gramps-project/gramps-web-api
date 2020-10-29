"""Tests for the `gramps_webapi.api` module using example_gramps."""

import unittest
from typing import Dict, List

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_object_count, get_test_client
from .utils import check_empty


class TestPeople(unittest.TestCase):
    """Test cases for the /api/people endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_people_endpoint(self):
        """Test reponse for people."""
        rv = self.client.get("/api/people/")
        # check expected number of people found
        assert len(rv.json) == get_object_count("people")
        # check first record is expected person
        it = rv.json[0]
        assert it["gramps_id"] == "I0552"
        assert it["primary_name"]["first_name"] == "Martha"
        assert it["primary_name"]["surname_list"][0]["surname"] == "Nielsen"
        # check last record is expected person
        it = rv.json[get_object_count("people") - 1]
        assert it["gramps_id"] == "I2156"
        assert it["primary_name"]["first_name"] == "蘭"
        assert it["primary_name"]["surname_list"][0]["surname"] == "賈"

    def test_people_endpoint_422(self):
        """Test response for an invalid parm."""
        rv = self.client.get("/api/people/?junk_parm=1")
        # check 422 returned
        assert rv.status_code == 422

    def test_people_endpoint_gramps_id(self):
        """Test response for gramps_id parm."""
        rv = self.client.get("/api/people/?gramps_id=SOME_RANDOM_THING")
        # check response for bad gramps id
        assert rv.status_code == 404
        rv = self.client.get("/api/people/?gramps_id=I0044")
        # check only one record returned
        assert len(rv.json) == 1
        # check we have the expected record
        it = rv.json[0]
        assert it["gramps_id"] == "I0044"
        assert it["primary_name"]["first_name"] == "Lewis Anderson"
        assert it["primary_name"]["surname_list"][1]["surname"] == "Zieliński"

    def test_people_endpoint_strip(self):
        """Test response for strip parm."""
        rv = self.client.get("/api/people/?strip=1")
        # check 422 returned if passed argument
        assert rv.status_code == 422
        pl = self.client.get("/api/people/")
        rv = self.client.get("/api/people/?strip")
        # check all people that keys for empty items no longer in second object
        for item in pl.json:
            check_empty(item, rv.json[pl.json.index(item)])

    def test_people_endpoint_keys(self):
        """Test response for keys parm."""
        rv = self.client.get("/api/people/?keys")
        # check 422 returned if missing argument
        assert rv.status_code == 422
        rv = self.client.get("/api/people/?keys=handle")
        # check only handle was returned for the single key test
        for person in rv.json:
            assert len(person) == 1
            assert "handle" in person
        rv = self.client.get("/api/people/?keys=handle,primary_name,event_ref_list")
        # check only expected keys returned for the multi-key test
        for person in rv.json:
            assert len(person) == 3
            assert "handle" in person
            assert "primary_name" in person
            assert "event_ref_list" in person

    def test_people_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        rv = self.client.get("/api/people/?skipkeys")
        # check 422 returned if missing argument
        assert rv.status_code == 422
        rv = self.client.get(
            "/api/people/?skipkeys=handle,lds_ord_list,person_ref_list"
        )
        # check for expected key count and that keys were skipped
        for person in rv.json:
            assert len(person) == 18
            assert "handle" not in person
            assert "lds_ord_list" not in person
            assert "person_ref_list" not in person

    def test_people_endpoint_rules(self):
        """Test response for rules parm."""
        rv = self.client.get(
            '/api/people/?rules={"function":"or","rules":[{"name":"HasTag","values":["complete"]},{"name":"HasTag","values":["ToDo"]}]}'
        )
        # check for expected match count using an or filter
        assert len(rv.json) == 2
        rv = self.client.get(
            '/api/people/?rules={"function":"xor","rules":[{"name":"IsFemale"},{"name":"MultipleMarriages"}]}'
        )
        # check for expected match count using an xor filter
        assert len(rv.json) == 958
        rv = self.client.get(
            '/api/people/?rules={"rules":[{"name":"IsMale"},{"name":"MultipleMarriages"}]}'
        )
        # check for expected match count using an and filter
        assert len(rv.json) == 28
        rv = self.client.get(
            '/api/people/?rules={"invert":true,"rules":[{"name":"IsMale"},{"name":"MultipleMarriages"}]}'
        )
        # check for expected match count using an invert for the previous filter
        assert len(rv.json) == 2129

    def test_people_endpoint_profile(self):
        """Test response for profile parm."""
        rv = self.client.get("/api/people/?profile=1")
        # check 422 returned if passed argument
        assert rv.status_code == 422
        rv = self.client.get("/api/people/?profile")
        # check expected number of people found
        assert len(rv.json) == 2157
        # check first record is expected person
        it = rv.json[0]
        assert it["gramps_id"] == "I0552"
        assert it["primary_name"]["first_name"] == "Martha"
        assert it["primary_name"]["surname_list"][0]["surname"] == "Nielsen"
        # check some key expected profile attributes present
        assert it["profile"]["name_given"] == "Martha"
        assert it["profile"]["name_surname"] == "Nielsen"
        assert it["profile"]["sex"] == "F"
        assert it["profile"]["families"][0]["father"]["name_given"] == "Robert Sr."
        assert it["profile"]["families"][0]["father"]["name_surname"] == "Adkins"
        assert it["profile"]["families"][0]["mother"]["name_given"] == "Martha"
        assert it["profile"]["families"][0]["mother"]["name_surname"] == "Nielsen"
        assert it["profile"]["families"][0]["children"][0] == {
            "birth": {
                "date": "after 1737-10-01",
                "place": "Maryville, MO, USA",
                "type": "Birth",
            },
            "death": {
                "date": "1787-05-20",
                "place": "Wooster, OH, USA",
                "type": "Death",
            },
            "handle": "E04KQC637O9JLP5PNM",
            "name_given": "John",
            "name_surname": "Adkins",
            "sex": "M",
        }
        # check last record is expected person
        it = rv.json[2156]
        assert it["gramps_id"] == "I2156"
        assert it["primary_name"]["first_name"] == "蘭"
        assert it["primary_name"]["surname_list"][0]["surname"] == "賈"
        assert it["profile"]["name_given"] == "蘭"
        assert it["profile"]["name_surname"] == "賈"

    def test_people_endpoint_extend(self):
        """Test response for extend parm."""
        rv = self.client.get("/api/people/?extend=all&gramps_id=I0044")
        # check all expected extended fields present with proper object counts
        it = rv.json[0]
        assert len(it["extended"]) == 9
        assert len(it["extended"]["citations"]) == 3
        assert len(it["extended"]["events"]) == 3
        assert len(it["extended"]["families"]) == 1
        assert len(it["extended"]["media"]) == 2
        assert len(it["extended"]["notes"]) == 4
        assert len(it["extended"]["parent_families"]) == 1
        assert len(it["extended"]["people"]) == 1
        assert len(it["extended"]["primary_parent_family"]["child_ref_list"]) == 12
        assert len(it["extended"]["tags"]) == 1
        rv = self.client.get("/api/people/?extend=citation_list&gramps_id=I0044")
        # check only citations present
        it = rv.json[0]
        assert len(it["extended"]) == 1
        assert len(it["extended"]["citations"]) == 3
        rv = self.client.get("/api/people/?extend=event_ref_list&gramps_id=I0044")
        # check only events present
        it = rv.json[0]
        assert len(it["extended"]) == 1
        assert len(it["extended"]["events"]) == 3
        rv = self.client.get("/api/people/?extend=families&gramps_id=I0044")
        # check only families present
        it = rv.json[0]
        assert len(it["extended"]) == 1
        assert len(it["extended"]["families"]) == 1
        rv = self.client.get("/api/people/?extend=media_list&gramps_id=I0044")
        # check only media present
        it = rv.json[0]
        assert len(it["extended"]) == 1
        assert len(it["extended"]["media"]) == 2
        rv = self.client.get("/api/people/?extend=note_list&gramps_id=I0044")
        # check only notes present
        it = rv.json[0]
        assert len(it["extended"]) == 1
        assert len(it["extended"]["notes"]) == 4
        rv = self.client.get("/api/people/?extend=parent_families&gramps_id=I0044")
        # check only parent_families present
        it = rv.json[0]
        assert len(it["extended"]) == 1
        assert len(it["extended"]["parent_families"]) == 1
        rv = self.client.get("/api/people/?extend=person_ref_list&gramps_id=I0044")
        # check only people present
        it = rv.json[0]
        assert len(it["extended"]) == 1
        assert len(it["extended"]["people"]) == 1
        rv = self.client.get(
            "/api/people/?extend=primary_parent_family&gramps_id=I0044"
        )
        # check only primary_parent_family present
        it = rv.json[0]
        assert len(it["extended"]) == 1
        assert len(it["extended"]["primary_parent_family"]["child_ref_list"]) == 12
        rv = self.client.get("/api/people/?extend=tag_list&gramps_id=I0044")
        # check only tags present
        it = rv.json[0]
        assert len(it["extended"]) == 1
        assert len(it["extended"]["tags"]) == 1
        rv = self.client.get("/api/people/?extend=tag_list,media_list&gramps_id=I0044")
        # check multiple tags work as expected
        it = rv.json[0]
        assert len(it["extended"]) == 2
        assert len(it["extended"]["tags"]) == 1
        assert len(it["extended"]["media"]) == 2

    def test_people_endpoint_schema(self):
        """Test the full people schema with extensions."""
        rv = self.client.get("/api/people/?extend=all&profile")
        # check expected number of people found
        assert len(rv.json) == get_object_count("people")
        # check all records found conform to expected schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for person in rv.json:
            validate(
                instance=person,
                schema=API_SCHEMA["definitions"]["Person"],
                resolver=resolver,
            )


class TestPerson(unittest.TestCase):
    """Test cases for the /api/people/{handle} endpoint for a person."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_person_handle_endpoint_404(self):
        """Test response for a bad handle."""
        rv = self.client.get("/api/people/does_not_exist")
        # check we received 404 for non-existent person
        assert rv.status_code == 404

    def test_person_handle_endpoint(self):
        """Test base person response."""
        rv = self.client.get("/api/people/GNUJQCL9MD64AM56OH")
        it = rv.json
        # check expected person returned
        assert it["gramps_id"] == "I0044"
        assert it["primary_name"]["first_name"] == "Lewis Anderson"
        assert it["primary_name"]["surname_list"][1]["surname"] == "Zieliński"

    def test_person_handle_endpoint_422(self):
        """Test response for an invalid parm."""
        rv = self.client.get("/api/people/GNUJQCL9MD64AM56OH?junk_parm=1")
        # check only one record returned
        assert rv.status_code == 422

    def test_person_handle_endpoint_strip(self):
        """Test response for strip parm."""
        pl = self.client.get("/api/people/1QTJQCP5QMT2X7YJDK")
        rv = self.client.get("/api/people/1QTJQCP5QMT2X7YJDK?strip")
        # check keys for empty items no longer in second object
        check_empty(pl.json, rv.json)

    def test_person_handle_endpoint_keys(self):
        """Test response for keys parm."""
        rv = self.client.get("/api/people/1QTJQCP5QMT2X7YJDK?keys=handle")
        # check only handle was returned for the single key test
        assert len(rv.json) == 1
        assert "handle" in rv.json
        rv = self.client.get(
            "/api/people/1QTJQCP5QMT2X7YJDK?keys=handle,primary_name,event_ref_list"
        )
        # check only expected keys returned for the multi-key test
        assert len(rv.json) == 3
        assert "handle" in rv.json
        assert "primary_name" in rv.json
        assert "event_ref_list" in rv.json

    def test_person_handle_endpoint_skipkeys(self):
        """Test response for skipkeys parm."""
        rv = self.client.get(
            "/api/people/1QTJQCP5QMT2X7YJDK?skipkeys=handle,lds_ord_list,person_ref_list"
        )
        # check for expected key count and that keys were skipped
        assert len(rv.json) == 18
        assert "handle" not in rv.json
        assert "lds_ord_list" not in rv.json
        assert "person_ref_list" not in rv.json
