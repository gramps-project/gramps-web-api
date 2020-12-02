#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Note API resource."""

from typing import Dict

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.lib import Note
from gramps.gen.utils.grampslocale import GrampsLocale

from ..html import get_note_html
from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import get_extended_attributes


class NoteResourceHelper(GrampsObjectResourceHelper):
    """Note resource helper."""

    gramps_class_name = "Note"

    # supported formatted note formats (all lowercase!)
    FORMATS_SUPPORTED = ["html"]

    def object_extend(
        self, obj: Note, args: Dict, locale: GrampsLocale = glocale
    ) -> Note:
        """Extend note attributes as needed."""
        if "formats" in args:
            formats_allowed = [
                fmt.lower()
                for fmt in args["formats"]
                if fmt.lower() in set(self.FORMATS_SUPPORTED)
            ]
            obj.formatted = {
                fmt: self.get_formatted_note(note=obj, fmt=fmt)
                for fmt in formats_allowed
            }
        if "extend" in args:
            obj.extended = get_extended_attributes(self.db_handle, obj, args)
        return obj

    def get_formatted_note(self, note: Note, fmt: str) -> str:
        """Get the note text in a specific format."""
        if fmt.lower() == "html":
            return get_note_html(note)
        raise ValueError("Format {} not known or supported.".format(fmt))


class NoteResource(GrampsObjectProtectedResource, NoteResourceHelper):
    """Note resource."""


class NotesResource(GrampsObjectsProtectedResource, NoteResourceHelper):
    """Notes resource."""
