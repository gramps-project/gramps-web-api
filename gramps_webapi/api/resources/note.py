"""Note API resource."""

from gramps.gen.lib import Note

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)


class NoteResourceHelper(GrampsObjectResourceHelper):
    """Note resource helper."""

    gramps_class_name = "Note"

    def object_extend(self, obj, args) -> Note:
        """Extend note attributes as needed."""
        if args["extend"]:
            db = self.db
            obj.extended = {
                "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list]
            }
        return obj


class NoteResource(GrampsObjectProtectedResource, NoteResourceHelper):
    """Note resource."""


class NotesResource(GrampsObjectsProtectedResource, NoteResourceHelper):
    """Notes resource."""
