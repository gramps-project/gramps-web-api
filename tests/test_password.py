#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Unit tests for `gramps_webapi.util.password`."""

import unittest

from gramps_webapi.util.passwords import hash_password, verify_password


class TestSQLAuth(unittest.TestCase):
    def test_pwhash(self):
        pwhash = hash_password("Xels")
        assert verify_password("Xels", pwhash)
        assert not verify_password("Marmelade", pwhash)
        # again: to check that hash is different
        pwhash2 = hash_password("Xels")
        assert pwhash != pwhash2
        assert verify_password("Xels", pwhash2)
