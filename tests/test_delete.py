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

"""Tests for deleting objects with references."""

from unittest.mock import MagicMock

from gramps.gen.errors import HandleError

from gramps_webapi.api.resources.delete import delete_family


class FakeDb:
    """A database whose reference table holds an entry for a person that is gone."""

    def __init__(self, backlinks):
        self.backlinks = backlinks
        self.commit_note = MagicMock()
        self.remove_family = MagicMock()

    def find_backlink_handles(self, handle, include_classes=None):
        return iter(self.backlinks)

    def get_person_from_handle(self, handle):
        raise HandleError(f"Handle {handle} not found")

    def get_note_from_handle(self, handle):
        return MagicMock()

    def method(self, fmt, *args):
        return getattr(self, fmt % tuple(arg.lower() for arg in args))


def test_delete_family_skips_a_backlink_whose_object_is_gone():
    db_handle = FakeDb([("Person", "gone"), ("Note", "n0001")])
    trans = MagicMock()

    delete_family(db_handle, "f0001", trans)

    # the intact backlink is still cleaned up, and the family is gone
    db_handle.commit_note.assert_called_once()
    db_handle.remove_family.assert_called_once_with("f0001", trans)
