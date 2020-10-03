"""Note API resource."""

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)


class NoteResourceHelper(GrampsObjectResourceHelper):
    """Note resource helper."""

    gramps_class_name = "Note"

    def object_denormalize(self, obj):
        """Denormalize note attributes if needed."""
        return obj

    
class NoteResource(GrampsObjectProtectedResource, NoteResourceHelper):
    """Note resource."""


class NotesResource(GrampsObjectsProtectedResource, NoteResourceHelper):
    """Notes resource."""
