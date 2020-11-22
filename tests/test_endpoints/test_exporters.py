#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Tests for the /api/exporters endpoints using example_gramps."""

import unittest
from mimetypes import types_map

from jsonschema import RefResolver, validate

from . import API_SCHEMA, get_test_client


class TestExporters(unittest.TestCase):
    """Test cases for the /api/exporters endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_exporters_endpoint(self):
        """Test response for exporters listing."""
        # check valid response
        result = self.client.get("/api/exporters/")
        self.assertEqual(result.status_code, 200)
        self.assertIsInstance(result.json, type([]))
        # check response conforms to schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        for report in result.json:
            validate(
                instance=report,
                schema=API_SCHEMA["definitions"]["Exporter"],
                resolver=resolver,
            )
        # check bad query parm response
        result = self.client.get("/api/exporters/?test=1")
        self.assertEqual(result.status_code, 422)


class TestExporter(unittest.TestCase):
    """Test cases for the /api/exporters/{extension} endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_exporters_extension_endpoint(self):
        """Test response for a specific exporter."""
        # check response for invalid exporter
        result = self.client.get("/api/exporters/no_real_extension")
        self.assertEqual(result.status_code, 404)
        # check response for valid exporter
        result = self.client.get("/api/exporters/gramps")
        self.assertEqual(result.status_code, 200)
        self.assertIsInstance(result.json, type({}))
        # check response conforms to schema
        resolver = RefResolver(base_uri="", referrer=API_SCHEMA, store={"": API_SCHEMA})
        validate(
            instance=result.json,
            schema=API_SCHEMA["definitions"]["Exporter"],
            resolver=resolver,
        )
        # check bad query parm response
        result = self.client.get("/api/exporters/gramps?test=1")
        self.assertEqual(result.status_code, 422)


class TestExporterFile(unittest.TestCase):
    """Test cases for the /api/exporters/{extension}/file endpoint."""

    @classmethod
    def setUpClass(cls):
        """Test class setup."""
        cls.client = get_test_client()

    def test_exporters_extension_file_endpoint(self):
        """Test response for a fetching a specific export."""
        # check response for invalid export
        result = self.client.get("/api/exporters/no_real_extension/file")
        self.assertEqual(result.status_code, 404)
        # check response for valid export
        result = self.client.get("/api/exporters/gramps/file")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.mimetype, types_map[".gramps"])
        # check bad query parm response
        result = self.client.get("/api/exporters/gramps/file?test=1")
        self.assertEqual(result.status_code, 422)

    def test_exporters_extension_file_compress_parm(self):
        """Test compress parm."""
        # check compress enabled response
        result = self.client.get("/api/exporters/gramps/file?compress=0")
        self.assertEqual(result.status_code, 200)
        self.assertIn('<?xml version="1.0" encoding="UTF-8"?>', str(result.data))
        result = self.client.get("/api/exporters/gramps/file?compress=1")
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('<?xml version="1.0" encoding="UTF-8"?>', str(result.data))

    def test_exporters_extension_file_private_parm(self):
        """Test private parm."""
        # check private enabled works
        result = self.client.get("/api/exporters/ged/file?private=0")
        self.assertEqual(result.status_code, 200)
        self.assertIn("1 SSN 123-456-7890", str(result.data))
        result = self.client.get("/api/exporters/ged/file?reference=1")
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("1 SSN 123-456-7890", str(result.data))

    def test_exporters_extension_file_living_parms(self):
        """Test living filter."""
        # check response bad option
        result = self.client.get("/api/exporters/gramps/file?living=NoOneReal")
        self.assertEqual(result.status_code, 422)
        # check normal response
        result = self.client.get("/api/exporters/gramps/file?living=IncludeAdd")
        self.assertEqual(result.status_code, 200)
        # check response for exclude all using a year offset
        result = self.client.get(
            "/api/exporters/gramps/file?compress=0&living=ExcludeAll&current_year=1912"
        )
        self.assertEqual(result.status_code, 200)
        self.assertIn('<person handle="_GNUJQCL9MD64AM56OH"', str(result.data))
        result = self.client.get(
            "/api/exporters/gramps/file?compress=0&living=ExcludeAll&current_year=1911"
        )
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('<person handle="_GNUJQCL9MD64AM56OH"', str(result.data))
        # check response for exclude all with year offset and years after death
        result = self.client.get(
            "/api/exporters/gramps/file?compress=0&living=ExcludeAll"
            + "&current_year=1914&years_after_death=5"
        )
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('<person handle="_GNUJQCL9MD64AM56OH"', str(result.data))
        # check response for last name only
        result = self.client.get(
            "/api/exporters/gramps/file?compress=0&living=LastNameOnly"
            + "&current_year=1914&years_after_death=5"
        )
        self.assertEqual(result.status_code, 200)
        self.assertIn("<first>[Living]</first>", str(result.data))
        self.assertNotIn("<surname>[Living]</surname>", str(result.data))
        # check response for replace complete name
        result = self.client.get(
            "/api/exporters/gramps/file?compress=0&living=ReplaceCompleteName"
            + "&current_year=1914&years_after_death=5"
        )
        self.assertEqual(result.status_code, 200)
        self.assertIn("<first>[Living]</first>", str(result.data))
        self.assertIn("<surname>[Living]</surname>", str(result.data))

    def test_exporters_extension_file_person_parms(self):
        """Test person filter."""
        # check response missing gramps_id or handle
        result = self.client.get("/api/exporters/gramps/file?person=Descendants")
        self.assertEqual(result.status_code, 422)
        # check response gramps id no person filter
        result = self.client.get("/api/exporters/gramps/file?gramps_id=I0044")
        self.assertEqual(result.status_code, 422)
        # check response with both provided
        result = self.client.get(
            "/api/exporters/gramps/file?person=Descendants&gramps_id=I0044"
        )
        self.assertEqual(result.status_code, 200)
        # check response handle no person filter
        result = self.client.get("/api/exporters/gramps/file?handle=GNUJQCL9MD64AM56OH")
        self.assertEqual(result.status_code, 422)
        # check response with both provided
        result = self.client.get(
            "/api/exporters/gramps/file?person=Descendants&handle=GNUJQCL9MD64AM56OH"
        )
        self.assertEqual(result.status_code, 200)
        # check descendant families response
        result = self.client.get(
            "/api/exporters/gramps/file?person=DescendantFamilies&gramps_id=I0044"
        )
        self.assertEqual(result.status_code, 200)
        # check ancestors response
        result = self.client.get(
            "/api/exporters/gramps/file?person=Ancestors&gramps_id=I0044"
        )
        self.assertEqual(result.status_code, 200)
        # check common ancestors response
        result = self.client.get(
            "/api/exporters/gramps/file?person=CommonAncestor&gramps_id=I0044"
        )
        self.assertEqual(result.status_code, 200)
        # create a custom person filter and check response with it and then clean it up
        payload = {
            "comment": "Test person export custom filter",
            "name": "PersonExportCustomFilter",
            "rules": [{"name": "IsMale"}],
        }
        result = self.client.post("/api/filters/people", json=payload)
        self.assertEqual(result.status_code, 201)
        result = self.client.get("/api/filters/people/PersonExportCustomFilter")
        self.assertEqual(result.status_code, 200)
        result = self.client.get(
            "/api/exporters/gramps/file?compress=0&person=PersonExportCustomFilter"
            + "&gramps_id=I0044"
        )
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("02NKQC5GOZFLSUSMW3", str(result.data))
        result = self.client.delete("/api/filters/people/PersonExportCustomFilter")
        self.assertEqual(result.status_code, 200)
        # check response non-existent custom filter
        result = self.client.get(
            "/api/exporters/gramps/file?person=SomeFakeCustomFilter&gramps_id=I0044"
        )
        self.assertEqual(result.status_code, 422)

    def test_exporters_extension_file_event_parm(self):
        """Test event filter."""
        # check response non-existent custom filter
        result = self.client.get("/api/exporters/gramps/file?event=SomeFakeEventFilter")
        self.assertEqual(result.status_code, 422)
        # create a custom event filter and check response with it and then clean it up
        payload = {
            "comment": "Test event export custom filter",
            "name": "EventExportCustomFilter",
            "rules": [{"name": "HasType", "values": ["Death"]}],
        }
        result = self.client.post("/api/filters/events", json=payload)
        self.assertEqual(result.status_code, 201)
        result = self.client.get(
            "/api/exporters/gramps/file?compress=0&event=EventExportCustomFilter"
        )
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("a5af0eb698f29568502", str(result.data))
        result = self.client.delete("/api/filters/events/EventExportCustomFilter")
        self.assertEqual(result.status_code, 200)

    def test_exporters_extension_file_note_parm(self):
        """Test note filter."""
        # check response non-existent custom filter
        result = self.client.get("/api/exporters/gramps/file?note=SomeFakeNoteFilter")
        self.assertEqual(result.status_code, 422)
        # create a custom note filter and check response with it and then clean it up
        payload = {
            "comment": "Test note export custom filter",
            "name": "NoteExportCustomFilter",
            "rules": [{"name": "HasType", "values": ["Person Note"]}],
        }
        result = self.client.post("/api/filters/notes", json=payload)
        self.assertEqual(result.status_code, 201)
        result = self.client.get(
            "/api/exporters/gramps/file?compress=0&note=NoteExportCustomFilter"
        )
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("ac380498bac48eedee8", str(result.data))
        result = self.client.delete("/api/filters/notes/NoteExportCustomFilter")
        self.assertEqual(result.status_code, 200)

    def test_exporters_extension_file_reference_parm(self):
        """Test reference parm."""
        # check reference enabled works
        result = self.client.get("/api/exporters/ged/file?reference=0")
        self.assertEqual(result.status_code, 200)
        self.assertIn("1 CONT Test link source: World of the Wierd", str(result.data))
        result = self.client.get("/api/exporters/ged/file?reference=1")
        self.assertEqual(result.status_code, 200)
        self.assertNotIn(
            "1 CONT Test link source: World of the Wierd", str(result.data)
        )

    def test_exporters_extension_file_sequence_parm(self):
        """Test sequence parm."""
        # check setting a short non-default order
        result = self.client.get(
            "/api/exporters/gramps/file?sequence=person,living,privacy"
        )
        self.assertEqual(result.status_code, 200)
        # check setting with a bad/misspelt option
        result = self.client.get(
            "/api/exporters/gramps/file?sequence=peron,living,privacy"
        )
        self.assertEqual(result.status_code, 422)

    def test_exporters_extension_file_csv_parms(self):
        """Test csv file options."""
        # check base response as all options default to on
        result = self.client.get("/api/exporters/csv/file")
        self.assertEqual(result.status_code, 200)
        self.assertIn('[P0000],"OH, USA",OH,State,,,,[P0957],', str(result.data))
        self.assertIn(
            "[I2005],Allen,Joseph,,,,,male,1692-05-17,,,,,,,,,,,,", str(result.data)
        )
        self.assertIn("[F0001],[I0005],[I0006],1974-08-10,[P1385],,", str(result.data))
        self.assertIn("[F0001],[I0004]", str(result.data))
        # check places disabled, name gets returned instead
        result = self.client.get("/api/exporters/csv/file?include_places=0")
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('[P0000],"OH, USA",OH,State,,,,[P0957],', str(result.data))
        self.assertIn(
            "[I2005],Allen,Joseph,,,,,male,1692-05-17,,,,,,,,,,,,", str(result.data)
        )
        self.assertNotIn(
            "[F0001],[I0005],[I0006],1974-08-10,[P1385],,", str(result.data)
        )
        self.assertIn(
            '[F0001],[I0005],[I0006],1974-08-10,"Worthington, MN, USA",,',
            str(result.data),
        )
        self.assertIn("[F0001],[I0004]", str(result.data))
        # check children disabled
        result = self.client.get("/api/exporters/csv/file?include_children=0")
        self.assertEqual(result.status_code, 200)
        self.assertIn('[P0000],"OH, USA",OH,State,,,,[P0957],', str(result.data))
        self.assertIn(
            "[I2005],Allen,Joseph,,,,,male,1692-05-17,,,,,,,,,,,,", str(result.data)
        )
        self.assertIn("[F0001],[I0005],[I0006],1974-08-10,[P1385],,", str(result.data))
        self.assertNotIn("[F0001],[I0004]", str(result.data))
        # check marriages disabled
        result = self.client.get("/api/exporters/csv/file?include_marriages=0")
        self.assertEqual(result.status_code, 200)
        self.assertIn('[P0000],"OH, USA",OH,State,,,,[P0957],', str(result.data))
        self.assertIn(
            "[I2005],Allen,Joseph,,,,,male,1692-05-17,,,,,,,,,,,,", str(result.data)
        )
        self.assertNotIn(
            "[F0001],[I0005],[I0006],1974-08-10,[P1385],,", str(result.data)
        )
        self.assertIn("[F0001],[I0004]", str(result.data))
        # check individuals disabled
        result = self.client.get("/api/exporters/csv/file?include_individuals=0")
        self.assertEqual(result.status_code, 200)
        self.assertIn('[P0000],"OH, USA",OH,State,,,,[P0957],', str(result.data))
        self.assertNotIn(
            "[I2005],Allen,Joseph,,,,,male,1692-05-17,,,,,,,,,,,,", str(result.data)
        )
        self.assertIn("[F0001],[I0005],[I0006],1974-08-10,[P1385],,", str(result.data))
        self.assertIn("[F0001],[I0004]", str(result.data))

    def test_exporters_extension_file_each_one(self):
        """Test one of each available exporter."""
        result_set = self.client.get("/api/exporters/")
        bad_exporters = []
        for exporter in result_set.json:
            result = self.client.get(
                "/api/exporters/" + exporter["extension"] + "/file"
            )
            if result.status_code != 200:
                bad_exporters.append(exporter)
        self.assertEqual(bad_exporters, [])

    # Note we do not test include_media and include_witness as they are present to
    # support the third party gedcom2 export plugin
