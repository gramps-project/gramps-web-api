"""Note API resource."""

from typing import Dict

from gramps.gen.lib import Note

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

    def object_extend(self, obj: Note, args: Dict) -> Note:
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
