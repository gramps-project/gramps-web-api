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
import os
import tempfile
import unittest

from gramps_webapi.api.resources.util import remove_mediapath_from_gramps_xml


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


if __name__ == "__main__":
    unittest.main()
