"""Note API resource."""

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)


class NoteResourceHelper(GrampsObjectResourceHelper):
    """Note resource helper."""

    gramps_class_name = "Note"


class NoteResource(GrampsObjectProtectedResource, NoteResourceHelper):
    """Note resource."""


class NotesResource(GrampsObjectsProtectedResource, NoteResourceHelper):
    """Notes resource."""
