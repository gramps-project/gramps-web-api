#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

"""Test that the server locale is always English."""

import os
import subprocess
import sys

_SCRIPT = """
import gramps_webapi
from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.datehandler import parser
print(GRAMPS_LOCALE.language[0])
print(GRAMPS_LOCALE.translation.gettext("Birth"))
print(type(parser).__name__)
"""


def test_server_locale_is_english_with_german_environment():
    """A German environment does not change the Gramps locale."""
    env = {**os.environ, "LANGUAGE": "de", "LANG": "de_DE.UTF-8"}
    env.pop("LC_ALL", None)
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.split() == ["en", "Birth", "DateParser"]
