#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2023 David Straub
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

"""Note API resource."""

import json
from typing import Dict, Optional

from flask import abort
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.lib import Note
from gramps.gen.utils.grampslocale import GrampsLocale

from ..html import get_note_html
from ..util import abort_with_message
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
            if args.get("format_options"):
                try:
                    format_options = json.loads(args["format_options"])
                except json.JSONDecodeError:
                    abort_with_message(400, "Error parsing format options")
            else:
                format_options = None
            obj.formatted = {
                fmt: self.get_formatted_note(note=obj, fmt=fmt, options=format_options)
                for fmt in formats_allowed
            }
        if "extend" in args:
            obj.extended = get_extended_attributes(self.db_handle, obj, args)
        return obj

    def get_formatted_note(
        self, note: Note, fmt: str, options: Optional[Dict] = None
    ) -> str:
        """Get the note text in a specific format."""

        if fmt.lower() == "html":
            if options is not None:
                link_format = options.get("link_format")
            else:
                link_format = None
            return get_note_html(note, link_format=link_format)
        raise ValueError("Format {} not known or supported.".format(fmt))


class NoteResource(GrampsObjectProtectedResource, NoteResourceHelper):
    """Note resource."""


class NotesResource(GrampsObjectsProtectedResource, NoteResourceHelper):
    """Notes resource."""
