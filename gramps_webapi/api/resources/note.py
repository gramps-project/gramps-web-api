"""Note API resource."""

from .base import (GrampsObjectProtectedResource, GrampsObjectResourceHelper,
                   GrampsObjectsProtectedResource)


class NoteResourceHelper(GrampsObjectResourceHelper):
    """Note resource helper."""

    gramps_class_name = "Note"

    def object_extend(self, obj):
        """Extend note attributes as needed."""
        if self.extend_object:
            db = self.db
            obj.extended = {
                "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list]
            }
        return obj


class NoteResource(GrampsObjectProtectedResource, NoteResourceHelper):
    """Note resource."""


class NotesResource(GrampsObjectsProtectedResource, NoteResourceHelper):
    """Notes resource."""
