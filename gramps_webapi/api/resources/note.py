"""Note API resource."""

from typing import Dict

from gramps.gen.lib import Note

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import get_extended_attributes


class NoteResourceHelper(GrampsObjectResourceHelper):
    """Note resource helper."""

    gramps_class_name = "Note"

    def object_extend(self, obj: Note, args: Dict) -> Note:
        """Extend note attributes as needed."""
        if args["extend"]:
            db_handle = self.db_handle
            obj.extended = get_extended_attributes(db_handle, obj)
        return obj


class NoteResource(GrampsObjectProtectedResource, NoteResourceHelper):
    """Note resource."""


class NotesResource(GrampsObjectsProtectedResource, NoteResourceHelper):
    """Notes resource."""
