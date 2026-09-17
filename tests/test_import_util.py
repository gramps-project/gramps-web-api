#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David M. Straub
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

"""Tests for import utility functions."""

import gzip
import re
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from werkzeug.exceptions import HTTPException

from gramps_webapi.api.resources.util import (
    MAX_IMPORT_REPORT_CHARS,
    dry_run_import,
    remove_mediapath_from_gramps_xml,
    run_import,
    truncate_import_report,
)
from gramps_webapi.app import create_app

APP = create_app(
    {"TREE": "test", "SECRET_KEY": "test", "USER_DB_URI": "sqlite://"},
    config_from_env=False,
)


class TestRemoveMediapathFromGrampsXml(unittest.TestCase):
    """Test cases for removing mediapath tags from Gramps XML files."""

    def test_remove_mediapath_uncompressed(self):
        """Test removing mediapath from uncompressed XML."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN"
"http://gramps-project.org/xml/1.7.1/grampsxml.dtd">
<database xmlns="http://gramps-project.org/xml/1.7.1/">
  <header>
    <created date="2024-01-01" version="5.1.5"/>
  </header>
  <mediapath>/some/path/to/media</mediapath>
  <people>
    <person handle="_123" id="I0001">
      <gender>M</gender>
    </person>
  </people>
</database>
"""

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".gramps", delete=False
        ) as f:
            temp_file = f.name
            f.write(xml_content)

        try:
            remove_mediapath_from_gramps_xml(temp_file)

            with open(temp_file, "rb") as f:
                result = f.read()

            self.assertNotIn(b"<mediapath>", result)
            self.assertNotIn(b"/some/path/to/media", result)
            self.assertIn(b'<person handle="_123"', result)
            self.assertIn(b"<gender>M</gender>", result)
        finally:
            os.unlink(temp_file)

    def test_remove_mediapath_compressed(self):
        """Test removing mediapath from compressed (gzipped) XML."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN"
"http://gramps-project.org/xml/1.7.1/grampsxml.dtd">
<database xmlns="http://gramps-project.org/xml/1.7.1/">
  <header>
    <created date="2024-01-01" version="5.1.5"/>
  </header>
  <mediapath>/some/path/to/media</mediapath>
  <people>
    <person handle="_456" id="I0002">
      <gender>F</gender>
    </person>
  </people>
</database>
"""

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".gramps", delete=False
        ) as f:
            temp_file = f.name
            with gzip.open(f, "wb") as gz:
                gz.write(xml_content)

        try:
            remove_mediapath_from_gramps_xml(temp_file)

            # Read back and verify (should still be gzipped)
            with gzip.open(temp_file, "rb") as f:
                result = f.read()

            self.assertNotIn(b"<mediapath>", result)
            self.assertNotIn(b"/some/path/to/media", result)
            self.assertIn(b'<person handle="_456"', result)
            self.assertIn(b"<gender>F</gender>", result)
        finally:
            os.unlink(temp_file)

    def test_remove_empty_mediapath(self):
        """Test removing empty mediapath tag."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<database>
  <header>
    <created date="2024-01-01" version="5.1.5"/>
  </header>
  <mediapath/>
  <people>
    <person handle="_789" id="I0003">
      <gender>M</gender>
    </person>
  </people>
</database>
"""

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".gramps", delete=False
        ) as f:
            temp_file = f.name
            f.write(xml_content)

        try:
            remove_mediapath_from_gramps_xml(temp_file)

            with open(temp_file, "rb") as f:
                result = f.read()

            self.assertNotIn(b"<mediapath", result)
            self.assertIn(b'<person handle="_789"', result)
        finally:
            os.unlink(temp_file)

    def test_remove_mediapath_with_whitespace(self):
        """Test removing mediapath tag with various whitespace."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<database>
  <header>
    <created date="2024-01-01" version="5.1.5"/>
  </header>
  <mediapath  >  /path/with/spaces  </mediapath  >
  <people>
    <person handle="_999" id="I0004">
      <gender>U</gender>
    </person>
  </people>
</database>
"""

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".gramps", delete=False
        ) as f:
            temp_file = f.name
            f.write(xml_content)

        try:
            remove_mediapath_from_gramps_xml(temp_file)

            with open(temp_file, "rb") as f:
                result = f.read()

            self.assertNotIn(b"<mediapath", result)
            self.assertNotIn(b"/path/with/spaces", result)
            self.assertIn(b'<person handle="_999"', result)
        finally:
            os.unlink(temp_file)

    def test_remove_mediapath_multiline(self):
        """Test removing mediapath tag spanning multiple lines."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<database>
  <header>
    <created date="2024-01-01" version="5.1.5"/>
  </header>
  <mediapath>
    /very/long/path/to/media/files/that/might/span/multiple/lines
  </mediapath>
  <people>
    <person handle="_111" id="I0005">
      <gender>M</gender>
    </person>
  </people>
</database>
"""

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".gramps", delete=False
        ) as f:
            temp_file = f.name
            f.write(xml_content)

        try:
            remove_mediapath_from_gramps_xml(temp_file)

            with open(temp_file, "rb") as f:
                result = f.read()

            self.assertNotIn(b"<mediapath>", result)
            self.assertNotIn(b"multiple/lines", result)
            self.assertIn(b'<person handle="_111"', result)
        finally:
            os.unlink(temp_file)

    def test_no_mediapath_present(self):
        """Test file without mediapath tag remains unchanged (except formatting)."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<database>
  <header>
    <created date="2024-01-01" version="5.1.5"/>
  </header>
  <people>
    <person handle="_222" id="I0006">
      <gender>F</gender>
    </person>
  </people>
</database>
"""

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".gramps", delete=False
        ) as f:
            temp_file = f.name
            f.write(xml_content)

        try:
            remove_mediapath_from_gramps_xml(temp_file)

            with open(temp_file, "rb") as f:
                result = f.read()

            # Should not have mediapath and should still have person data
            self.assertNotIn(b"<mediapath", result)
            self.assertIn(b'<person handle="_222"', result)
            self.assertIn(b"<gender>F</gender>", result)
        finally:
            os.unlink(temp_file)

    def test_preserve_other_xml_structure(self):
        """Test that other XML structure is preserved correctly."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE database PUBLIC "-//Gramps//DTD Gramps XML 1.7.1//EN"
"http://gramps-project.org/xml/1.7.1/grampsxml.dtd">
<database xmlns="http://gramps-project.org/xml/1.7.1/">
  <header>
    <created date="2024-01-01" version="5.1.5"/>
    <researcher>
      <resname>Test Researcher</resname>
    </researcher>
  </header>
  <mediapath>/media/path</mediapath>
  <namemaps>
    <map type="group_as" key="Smith" value="Smyth"/>
  </namemaps>
  <people>
    <person handle="_333" id="I0007">
      <gender>M</gender>
      <name type="Birth Name">
        <first>John</first>
        <surname>Doe</surname>
      </name>
    </person>
  </people>
</database>
"""

        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".gramps", delete=False
        ) as f:
            temp_file = f.name
            f.write(xml_content)

        try:
            remove_mediapath_from_gramps_xml(temp_file)

            with open(temp_file, "rb") as f:
                result = f.read()

            # Verify mediapath is removed
            self.assertNotIn(b"<mediapath>", result)
            self.assertNotIn(b"/media/path", result)

            # Verify other structure is preserved
            self.assertIn(b"<header>", result)
            self.assertIn(b"<researcher>", result)
            self.assertIn(b"<resname>Test Researcher</resname>", result)
            self.assertIn(b"<namemaps>", result)
            self.assertIn(b'<map type="group_as"', result)
            self.assertIn(b"<people>", result)
            self.assertIn(b'<name type="Birth Name">', result)
            self.assertIn(b"<first>John</first>", result)
            self.assertIn(b"<surname>Doe</surname>", result)
        finally:
            os.unlink(temp_file)


class TestGedcom7ErrorHandling(unittest.TestCase):
    """Test cases for GEDCOM7 import error handling."""

    @patch("gramps_webapi.api.resources.util.detect_gedcom_major_version")
    @patch("gramps_webapi.api.resources.util.gramps_gedcom7")
    def test_gedcom7_valueerror_returns_422(self, mock_gedcom7, mock_detect_version):
        """Test that ValueError during GEDCOM7 import returns 422."""
        mock_detect_version.return_value = 7
        mock_gedcom7.import_gedcom.side_effect = ValueError("File is not UTF-8 encoded")

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".ged", delete=False) as f:
            temp_file = f.name
            f.write(b"dummy content")

        try:
            mock_db = MagicMock()

            # Create Flask app context for current_app
            with APP.app_context():
                with self.assertRaises(HTTPException) as cm:
                    run_import(
                        db_handle=mock_db,
                        file_name=temp_file,
                        extension="ged",
                        delete=True,
                    )

                # Verify 422 status code and message
                self.assertEqual(cm.exception.code, 422)
                self.assertIn("Invalid GEDCOM file", str(cm.exception.description))
                self.assertIn("UTF-8", str(cm.exception.description))

            # Verify file was deleted
            self.assertFalse(os.path.exists(temp_file))
        finally:
            # Clean up if test failed
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    @patch("gramps_webapi.api.resources.util.detect_gedcom_major_version")
    @patch("gramps_webapi.api.resources.util.gramps_gedcom7")
    def test_gedcom7_unexpected_error_returns_500(
        self, mock_gedcom7, mock_detect_version
    ):
        """Test that unexpected Exception during GEDCOM7 import returns 500."""
        mock_detect_version.return_value = 7
        mock_gedcom7.import_gedcom.side_effect = RuntimeError("Unexpected error")

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".ged", delete=False) as f:
            temp_file = f.name
            f.write(b"dummy content")

        try:
            mock_db = MagicMock()

            # Create Flask app context
            with APP.app_context():
                with self.assertRaises(HTTPException) as cm:
                    run_import(
                        db_handle=mock_db,
                        file_name=temp_file,
                        extension="ged",
                        delete=True,
                    )

                # Verify 500 status code and message
                self.assertEqual(cm.exception.code, 500)
                self.assertIn("Import failed", str(cm.exception.description))
                self.assertIn("Unexpected error", str(cm.exception.description))

            # Verify file was deleted
            self.assertFalse(os.path.exists(temp_file))
        finally:
            # Clean up if test failed
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    @patch("gramps_webapi.api.resources.util.detect_gedcom_major_version")
    @patch("gramps_webapi.api.resources.util.gramps_gedcom7")
    @patch("gramps_webapi.api.resources.util.os.remove")
    def test_gedcom7_cleanup_failure_doesnt_mask_error(
        self, mock_remove, mock_gedcom7, mock_detect_version
    ):
        """Test that file cleanup failures don't mask the original import error."""
        mock_detect_version.return_value = 7
        mock_gedcom7.import_gedcom.side_effect = ValueError("Invalid file")
        # Simulate file deletion failure
        mock_remove.side_effect = OSError("Permission denied")

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".ged", delete=False) as f:
            temp_file = f.name
            f.write(b"dummy content")

        try:
            mock_db = MagicMock()

            # Create Flask app context
            with APP.app_context():
                with self.assertRaises(HTTPException) as cm:
                    run_import(
                        db_handle=mock_db,
                        file_name=temp_file,
                        extension="ged",
                        delete=True,
                    )

                # Verify original 422 error is preserved, not OSError
                self.assertEqual(cm.exception.code, 422)
                self.assertIn("Invalid GEDCOM file", str(cm.exception.description))
                self.assertNotIn("Permission denied", str(cm.exception.description))

            # Verify os.remove was attempted
            mock_remove.assert_called_once_with(temp_file)
        finally:
            # Clean up
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    @patch("gramps_webapi.api.resources.util.detect_gedcom_major_version")
    @patch("gramps_webapi.api.resources.util.gramps_gedcom7")
    def test_gedcom7_no_delete_preserves_file(self, mock_gedcom7, mock_detect_version):
        """Test that file is preserved when delete=False."""
        mock_detect_version.return_value = 7
        mock_gedcom7.import_gedcom.side_effect = ValueError("Invalid file")

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".ged", delete=False) as f:
            temp_file = f.name
            f.write(b"dummy content")

        try:
            mock_db = MagicMock()

            # Create Flask app context
            with APP.app_context():
                with self.assertRaises(HTTPException):
                    run_import(
                        db_handle=mock_db,
                        file_name=temp_file,
                        extension="ged",
                        delete=False,  # Don't delete
                    )

            # Verify file was NOT deleted
            self.assertTrue(os.path.exists(temp_file))
        finally:
            # Clean up
            if os.path.exists(temp_file):
                os.unlink(temp_file)


GEDCOM_WITH_PROBLEMS = b"""0 HEAD
1 SOUR TEST
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
1 CHAR UTF-8
0 @I1@ INDI
1 NAME John /Smith/
1 BIRT
2 DATE 1 JAN 1900
2 QUAY 3
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I404@
0 TRLR
"""


class TestImportReport(unittest.TestCase):
    """Test cases for capturing the importer's diagnostic messages."""

    @staticmethod
    def _import(content: bytes) -> list[str]:
        """Import GEDCOM content into a scratch database, return the messages."""
        from gramps.gen.db.utils import make_database

        with tempfile.NamedTemporaryFile(suffix=".ged", delete=False) as f:
            f.write(content)
            temp_file = f.name
        db_handle = make_database("sqlite")
        db_handle.load(":memory:")
        db_handle.set_feature("skip-import-additions", True)
        try:
            with APP.app_context():
                return run_import(
                    db_handle=db_handle,
                    file_name=temp_file,
                    extension="ged",
                    delete=False,
                )
        finally:
            db_handle.close()
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_report_contains_unsupported_tag(self):
        """The report names a tag the importer could not handle."""
        messages = self._import(GEDCOM_WITH_PROBLEMS)
        report = "\n".join(messages)
        self.assertIn("QUAY", report)
        self.assertIn("not supported", report)

    def test_report_contains_dangling_reference(self):
        """The report flags a reference to a record missing from the file."""
        report = "\n".join(self._import(GEDCOM_WITH_PROBLEMS))
        self.assertIn("I404", report)

    def test_clean_file_reports_no_errors(self):
        """A file without problems still yields the importer's summary line."""
        clean = GEDCOM_WITH_PROBLEMS.replace(b"2 QUAY 3\n", b"").replace(
            b"0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I404@\n", b""
        )
        report = "\n".join(self._import(clean))
        self.assertIn("No errors detected", report)


class TestTruncateImportReport(unittest.TestCase):
    """Test cases for capping the size of importer diagnostics."""

    def test_short_report_passes_through(self):
        """A report within budget is returned unchanged."""
        messages = ["GEDCOM import report: 1 errors detected\nsomething went wrong"]
        self.assertEqual(truncate_import_report(messages), messages)

    def test_empty_report_passes_through(self):
        """An empty message list is handled."""
        self.assertEqual(truncate_import_report([]), [])

    def test_long_report_is_truncated(self):
        """An oversized report is cut down and the omitted lines counted."""
        lines = [f"Error on line {i}: something went wrong" for i in range(10000)]
        result = truncate_import_report(["\n".join(lines)], max_chars=1000)
        self.assertLess(sum(len(m) for m in result), 1200)
        self.assertIn("Report truncated", result[-1])
        # the beginning is kept, so the importer's summary line survives
        self.assertIn("Error on line 0:", result[0])

    def test_truncation_counts_all_omitted_lines(self):
        """The omitted count covers every line that was dropped."""
        lines = [f"line {i}" for i in range(500)]
        result = truncate_import_report(["\n".join(lines)], max_chars=100)
        match = re.search(r"(\d+) further lines omitted", result[-1])
        assert match is not None
        kept = sum(m.count("\n") + 1 for m in result[:-1])
        self.assertEqual(int(match.group(1)) + kept, 500)

    def test_truncation_cuts_at_line_boundary(self):
        """Truncation never leaves a partial line."""
        lines = [f"line {i}" for i in range(500)]
        result = truncate_import_report(["\n".join(lines)], max_chars=100)
        for line in result[0].split("\n"):
            self.assertRegex(line, r"^line \d+$")

    def test_default_cap_is_applied(self):
        """The default budget is used when none is given."""
        huge = "\n".join(f"line {i}" for i in range(MAX_IMPORT_REPORT_CHARS))
        result = truncate_import_report([huge])
        self.assertLessEqual(sum(len(m) for m in result), MAX_IMPORT_REPORT_CHARS + 200)


class TestDryRunImportReport(unittest.TestCase):
    """Test cases for diagnostics returned by a dry run."""

    def test_dry_run_returns_counts_and_messages(self):
        """A dry run reports what a real import would complain about."""
        with tempfile.NamedTemporaryFile(suffix=".ged", delete=False) as f:
            f.write(GEDCOM_WITH_PROBLEMS)
            temp_file = f.name
        try:
            with APP.app_context():
                result = dry_run_import(file_name=temp_file, extension="ged")
            assert result is not None
            self.assertEqual(result["people"], 2)
            report = "\n".join(result["messages"])
            self.assertIn("QUAY", report)
            self.assertIn("I404", report)
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
