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

"""Tests for the /api/exporters endpoints using example_gramps."""

import unittest
from mimetypes import types_map

from . import BASE_URL, get_test_client
from .checks import (
    check_conforms_to_schema,
    check_invalid_semantics,
    check_requires_token,
    check_resource_missing,
    check_success,
)
from .util import fetch_header

TEST_URL = BASE_URL + "/exporters/"


class TestExporters(unittest.TestCase):
    """Test cases for the /api/exporters endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_exporters_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL)

    def test_get_exporters_conforms_to_schema(self):
        """Test conformity to schema."""
        check_conforms_to_schema(self, TEST_URL, "Exporter")

    def test_get_exporters_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "?test=1")


class TestExportersExtension(unittest.TestCase):
    """Test cases for the /api/exporters/{extension} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_exporters_extension_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "gramps")

    def test_get_exporters_extension_conforms_to_schema(self):
        """Test conformity to schema."""
        check_conforms_to_schema(self, TEST_URL + "gramps", "Exporter")

    def test_get_exporters_extension_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "missing")

    def test_get_exporters_extension_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "gramps?test=1")


class TestExportersExtensionFile(unittest.TestCase):
    """Test cases for the /api/exporters/{extension}/file endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_get_exporters_extension_file_requires_token(self):
        """Test authorization required."""
        check_requires_token(self, TEST_URL + "gramps/file")

    def test_get_exporters_extension_file_expected_result(self):
        """Test response for a fetching a specific export."""
        rv = check_success(self, TEST_URL + "gramps/file", full=True)
        self.assertEqual(rv.mimetype, types_map[".gramps"])

    def test_get_exporters_extension_file_missing_content(self):
        """Test response for missing content."""
        check_resource_missing(self, TEST_URL + "missing/file")

    def test_get_exporters_extension_file_validate_semantics(self):
        """Test invalid parameters and values."""
        check_invalid_semantics(self, TEST_URL + "gramps/file?test=1")
        check_invalid_semantics(self, TEST_URL + "gramps/file?compress=1&test=1")

    def test_get_exporters_extension_file_parameter_compress_validate_semantics(self):
        """Test compress parameter."""
        check_invalid_semantics(
            self, TEST_URL + "gramps/file?compress", check="boolean"
        )

    def test_get_exporters_extension_file_parameter_compress_expected_result(self):
        """Test compress parameter."""
        rv = check_success(self, TEST_URL + "gramps/file?compress=0", full=True)
        self.assertIn(b'<?xml version="1.0" encoding="UTF-8"?>', rv.data)
        rv = check_success(self, TEST_URL + "gramps/file?compress=1", full=True)
        self.assertNotIn(b'<?xml version="1.0" encoding="UTF-8"?>', rv.data)

    def test_get_exporters_extension_file_parameter_private_validate_semantics(self):
        """Test invalid private parameter and values."""
        check_invalid_semantics(self, TEST_URL + "gramps/file?private", check="boolean")

    def test_get_exporters_extension_file_parameter_private_expected_result(self):
        """Test private parameter."""
        rv = check_success(
            self, TEST_URL + "gramps/file?compress=0&private=0", full=True
        )
        self.assertIn(b"123-456-7890", rv.data)
        rv = check_success(
            self, TEST_URL + "gramps/file?compress=0&private=1", full=True
        )
        self.assertNotIn(b"123-456-7890", rv.data)

    def test_get_exporters_extension_file_parameter_living_validate_semantics(self):
        """Test invalid living parameter with bad filter."""
        check_invalid_semantics(self, TEST_URL + "gramps/file?living=NoOneReal")

    def test_get_exporters_extension_file_parameter_living_include_all(self):
        """Test living parameter with include all filter."""
        check_success(self, TEST_URL + "gramps/file?living=IncludeAll")

    def test_get_exporters_extension_file_parameter_living_exclude_all_use_year(self):
        """Test living parameter with exclude all filter and current year."""
        rv = check_success(
            self,
            TEST_URL + "gramps/file?compress=0&living=ExcludeAll&current_year=1912",
            full=True,
        )
        self.assertIn(b'<person handle="_GNUJQCL9MD64AM56OH"', rv.data)
        rv = check_success(
            self,
            TEST_URL + "gramps/file?compress=0&living=ExcludeAll&current_year=1911",
            full=True,
        )
        self.assertNotIn(b'<person handle="_GNUJQCL9MD64AM56OH"', rv.data)

    def test_get_exporters_extension_file_parameter_living_exclude_all_after_death(
        self,
    ):
        """Test living parameter with exclude all filter and years after death."""
        rv = check_success(
            self,
            TEST_URL
            + "gramps/file?compress=0&living=ExcludeAll"
            + "&current_year=1914&years_after_death=5",
            full=True,
        )
        self.assertNotIn(b'<person handle="_GNUJQCL9MD64AM56OH"', rv.data)

    def test_get_exporters_extension_file_parameter_living_exclude_all_bad_options(
        self,
    ):
        """Test living parameter with exclude all filter with bad options."""
        check_invalid_semantics(
            self,
            TEST_URL + "gramps/file?compress=0&living=ExcludeAll&current_year",
        )
        check_invalid_semantics(
            self,
            TEST_URL + "gramps/file?compress=0&living=ExcludeAll&current_year=abc",
        )
        check_invalid_semantics(
            self,
            TEST_URL
            + "gramps/file?compress=0&living=ExcludeAll"
            + "&current_year=1914&years_after_death",
        )
        check_invalid_semantics(
            self,
            TEST_URL
            + "gramps/file?compress=0&living=ExcludeAll"
            + "&current_year=1914&years_after_death=abc",
        )

    def test_get_exporters_extension_file_parameter_living_last_name_only(self):
        """Test living parameter with last name only filter."""
        rv = check_success(
            self,
            TEST_URL
            + "gramps/file?compress=0&living=LastNameOnly"
            + "&current_year=1914&years_after_death=5",
            full=True,
        )
        self.assertIn(b"<first>[Living]</first>", rv.data)
        self.assertNotIn(b"<surname>[Living]</surname>", rv.data)

    def test_get_exporters_extension_file_parameter_living_replace_complete_name(self):
        """Test living parameter with replace complete name filter."""
        rv = check_success(
            self,
            TEST_URL
            + "gramps/file?compress=0&living=ReplaceCompleteName"
            + "&current_year=1914&years_after_death=5",
            full=True,
        )
        self.assertIn(b"<first>[Living]</first>", rv.data)
        self.assertIn(b"<surname>[Living]</surname>", rv.data)

    def test_get_exporters_extension_file_parameter_person_validate_semantics(self):
        """Test invalid person parameter and values."""
        check_invalid_semantics(self, TEST_URL + "gramps/file?person=Descendants")
        check_invalid_semantics(self, TEST_URL + "gramps/file?gramps_id=I0044")
        check_invalid_semantics(
            self, TEST_URL + "gramps/file?handle=GNUJQCL9MD64AM56OH"
        )

    def test_get_exporters_extension_file_parameter_person_descendant_with_gramps_id(
        self,
    ):
        """Test person parameter descendant filter with gramps id."""
        check_success(
            self,
            TEST_URL + "gramps/file?person=Descendants&gramps_id=I0044",
        )

    def test_get_exporters_extension_file_parameter_person_descendant_with_handle(self):
        """Test person parameter descendant filter with handle."""
        check_success(
            self,
            TEST_URL + "gramps/file?person=Descendants&handle=GNUJQCL9MD64AM56OH",
        )

    def test_get_exporters_extension_file_parameter_person_descendant_families(self):
        """Test person parameter descendant families filter."""
        check_success(
            self,
            TEST_URL + "gramps/file?person=DescendantFamilies&gramps_id=I0044",
        )

    def test_get_exporters_extension_file_parameter_person_ancestor_families(self):
        """Test person parameter ancestors filter."""
        check_success(
            self,
            TEST_URL + "gramps/file?person=Ancestors&gramps_id=I0044",
        )

    def test_get_exporters_extension_file_parameter_person_common_ancestor_families(
        self,
    ):
        """Test person parameter common ancestors filter."""
        check_success(
            self,
            TEST_URL + "gramps/file?person=CommonAncestor&gramps_id=I0044",
        )

    def test_get_exporters_extension_file_parameter_person_custom_filter(self):
        """Test person parameter custom filter."""
        header = fetch_header(self.client)
        payload = {
            "comment": "Test person export custom filter",
            "name": "PersonExportCustomFilter",
            "rules": [{"name": "IsMale"}],
        }
        rv = self.client.post(
            BASE_URL + "/filters/people", json=payload, headers=header
        )
        self.assertEqual(rv.status_code, 201)
        rv = check_success(self, BASE_URL + "/filters/people/PersonExportCustomFilter")
        rv = check_success(
            self,
            TEST_URL
            + "gramps/file?compress=0&person=PersonExportCustomFilter"
            + "&gramps_id=I0044",
            full=True,
        )
        self.assertNotIn(b"02NKQC5GOZFLSUSMW3", rv.data)
        header = fetch_header(self.client)
        rv = self.client.delete(
            BASE_URL + "/filters/people/PersonExportCustomFilter", headers=header
        )
        self.assertEqual(rv.status_code, 200)

    def test_get_exporters_extension_file_parameter_person_missing_custom_filter(self):
        """Test person parameter missing custom filter."""
        check_invalid_semantics(
            self,
            TEST_URL + "gramps/file?person=SomeFakeCustomFilter&gramps_id=I0044",
        )

    def test_get_exporters_extension_file_parameter_event_custom_filter(self):
        """Test event parameter custom filter."""
        header = fetch_header(self.client)
        payload = {
            "comment": "Test event export custom filter",
            "name": "EventExportCustomFilter",
            "rules": [{"name": "HasType", "values": ["Death"]}],
        }
        rv = self.client.post(
            BASE_URL + "/filters/events", json=payload, headers=header
        )
        self.assertEqual(rv.status_code, 201)
        rv = check_success(self, BASE_URL + "/filters/events/EventExportCustomFilter")
        rv = check_success(
            self,
            TEST_URL + "gramps/file?compress=0&event=EventExportCustomFilter",
            full=True,
        )
        self.assertNotIn(b"a5af0eb698f29568502", rv.data)
        header = fetch_header(self.client)
        rv = self.client.delete(
            BASE_URL + "/filters/events/EventExportCustomFilter", headers=header
        )
        self.assertEqual(rv.status_code, 200)

    def test_get_exporters_extension_file_parameter_event_missing_custom_filter(self):
        """Test event parameter missing custom filter."""
        check_invalid_semantics(
            self, TEST_URL + "gramps/file?event=SomeFakeEventFilter"
        )

    def test_get_exporters_extension_file_parameter_note_custom_filter(self):
        """Test note parameter custom filter."""
        header = fetch_header(self.client)
        payload = {
            "comment": "Test note export custom filter",
            "name": "NoteExportCustomFilter",
            "rules": [{"name": "HasType", "values": ["Person Note"]}],
        }
        rv = self.client.post(BASE_URL + "/filters/notes", json=payload, headers=header)
        self.assertEqual(rv.status_code, 201)
        rv = check_success(self, BASE_URL + "/filters/notes/NoteExportCustomFilter")
        rv = check_success(
            self,
            TEST_URL + "gramps/file?compress=0&note=NoteExportCustomFilter",
            full=True,
        )
        self.assertNotIn(b"ac380498bac48eedee8", rv.data)
        header = fetch_header(self.client)
        rv = self.client.delete(
            BASE_URL + "/filters/notes/NoteExportCustomFilter", headers=header
        )
        self.assertEqual(rv.status_code, 200)

    def test_get_exporters_extension_file_parameter_note_missing_custom_filter(self):
        """Test note parameter missing custom filter."""
        check_invalid_semantics(self, TEST_URL + "gramps/file?note=SomeFakeNoteFilter")

    def test_get_exporters_extension_file_parameter_reference_validate_semantics(self):
        """Test invalid reference parameter and values."""
        check_invalid_semantics(self, TEST_URL + "ged/file?reference", check="boolean")

    def test_get_exporters_extension_file_parameter_reference_expected_result(self):
        """Test reference parameter."""
        rv = check_success(self, TEST_URL + "ged/file?reference=0", full=True)
        self.assertIn(b"1 CONT Test link source: World of the Wierd", rv.data)
        rv = check_success(self, TEST_URL + "ged/file?reference=1", full=True)
        self.assertNotIn(b"1 CONT Test link source: World of the Wierd", rv.data)

    def test_get_exporters_extension_file_parameter_sequence_validate_semantics(self):
        """Test invalid sequence parameters and values."""
        check_invalid_semantics(
            self,
            TEST_URL + "gramps/file?sequence=peron,living,privacy",
        )

    def test_get_exporters_extension_file_parameter_sequence_expected_result(self):
        """Test sequence parameter changing order."""
        check_success(
            self,
            TEST_URL + "gramps/file?sequence=living,privacy",
        )
        check_success(
            self,
            TEST_URL
            + "gramps/file?compress=0&living=ExcludeAll&current_year=1912&private=1",
        )

    def test_get_exporters_extension_file_csv_expected_result(self):
        """Test csv parameter file options defaults all enabled."""
        rv = check_success(self, TEST_URL + "csv/file", full=True)
        self.assertIn(b'[P0000],"OH, USA",OH,State,,,,[P0957],', rv.data)
        self.assertIn(b"[I2005],Allen,Joseph,,,,,,male,1692-05-17,,,,,,,,,,,", rv.data)
        self.assertIn(b"[F0001],[I0005],[I0006],1974-08-10,[P1385],,", rv.data)
        self.assertIn(b"[F0001],[I0004]", rv.data)

    def test_get_exporters_extension_file_csv_parameter_include_places_validate_semantics(
        self,
    ):
        """Test invalid include_places parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "csv/file?include_places", check="boolean"
        )

    def test_get_exporters_extension_file_csv_parameter_include_places_expected_result(
        self,
    ):
        """Test csv parameter file options with places disabled."""
        rv = check_success(self, TEST_URL + "csv/file?include_places=0", full=True)
        self.assertNotIn(b'[P0000],"OH, USA",OH,State,,,,[P0957],', rv.data)
        self.assertIn(b"[I2005],Allen,Joseph,,,,,,male,1692-05-17,,,,,,,,,,,", rv.data)
        self.assertNotIn(b"[F0001],[I0005],[I0006],1974-08-10,[P1385],,", rv.data)
        self.assertIn(
            b'[F0001],[I0005],[I0006],1974-08-10,"Worthington, MN, USA",,',
            rv.data,
        )
        self.assertIn(b"[F0001],[I0004]", rv.data)

    def test_get_exporters_extension_file_csv_parameter_include_children_validate_semantics(
        self,
    ):
        """Test invalid include_children parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "csv/file?include_children", check="boolean"
        )

    def test_get_exporters_extension_file_csv_parameter_include_children_expected_result(
        self,
    ):
        """Test csv parameter file options with children disabled."""
        rv = check_success(self, TEST_URL + "csv/file?include_children=0", full=True)
        self.assertIn(b'[P0000],"OH, USA",OH,State,,,,[P0957],', rv.data)
        self.assertIn(b"[I2005],Allen,Joseph,,,,,,male,1692-05-17,,,,,,,,,,,", rv.data)
        self.assertIn(b"[F0001],[I0005],[I0006],1974-08-10,[P1385],,", rv.data)
        self.assertNotIn(b"[F0001],[I0004]", rv.data)

    def test_get_exporters_extension_file_csv_parameter_include_marriages_validate_sematics(
        self,
    ):
        """Test invalid include_marriages parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "csv/file?include_marriages", check="boolean"
        )

    def test_get_exporters_extension_file_csv_parameter_include_marriages_expected_result(
        self,
    ):
        """Test csv parameter file options with marriages disabled."""
        rv = check_success(self, TEST_URL + "csv/file?include_marriages=0", full=True)
        self.assertIn(b'[P0000],"OH, USA",OH,State,,,,[P0957],', rv.data)
        self.assertIn(b"[I2005],Allen,Joseph,,,,,,male,1692-05-17,,,,,,,,,,,", rv.data)
        self.assertNotIn(b"[F0001],[I0005],[I0006],1974-08-10,[P1385],,", rv.data)
        self.assertIn(b"[F0001],[I0004]", rv.data)

    def test_get_exporters_extension_file_csv_parameter_include_individuals_validate_semantics(
        self,
    ):
        """Test invalid include_individuals parameter and values."""
        check_invalid_semantics(
            self, TEST_URL + "csv/file?include_individuals", check="boolean"
        )

    def test_get_exporters_extension_file_csv_parameter_include_individuals_expected_result(
        self,
    ):
        """Test csv parameter file options with individuals disabled."""
        rv = check_success(self, TEST_URL + "csv/file?include_individuals=0", full=True)
        self.assertIn(b'[P0000],"OH, USA",OH,State,,,,[P0957],', rv.data)
        self.assertNotIn(
            b"[I2005],Allen,Joseph,,,,,,male,1692-05-17,,,,,,,,,,,", rv.data
        )
        self.assertIn(b"[F0001],[I0005],[I0006],1974-08-10,[P1385],,", rv.data)
        self.assertIn(b"[F0001],[I0004]", rv.data)

    def test_get_exporters_extension_file_one_of_each(self):
        """Test one of each available exporter."""
        bad_exporters = []
        rv_set = check_success(self, TEST_URL)
        header = fetch_header(self.client)
        for exporter in rv_set:
            rv = self.client.get(
                TEST_URL + exporter["extension"] + "/file", headers=header
            )
            if rv.status_code != 200:
                bad_exporters.append(exporter)
        self.assertEqual(bad_exporters, [])

    # Note we do not test include_media and include_witness options as they are
    # present to support the third party gedcom2 export plugin


class TestExportersExtensionFilePost(unittest.TestCase):
    """Test cases for the /api/exporters/{extension}/file POST endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_export_xml(self):
        """Test the XML export."""
        header = fetch_header(self.client)
        res = self.client.post(f"{TEST_URL}gramps/file", headers=header)
        assert res.status_code == 201
