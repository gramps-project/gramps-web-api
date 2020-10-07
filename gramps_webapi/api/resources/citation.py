"""Citation API resource."""

from .base import (GrampsObjectProtectedResource, GrampsObjectResourceHelper,
                   GrampsObjectsProtectedResource)
from .util import get_media, get_source


class CitationResourceHelper(GrampsObjectResourceHelper):
    """Citation resource helper."""

    gramps_class_name = "Citation"

    def object_extend(self, obj):
        """Extend citation attributes as needed."""
        if self.extend_object:
            db = self.db
            obj.extended = {
                "media": get_media(db, obj),
                "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
                "source": get_source(db, obj.source_handle),
                "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list],
            }
        return obj


class CitationResource(GrampsObjectProtectedResource, CitationResourceHelper):
    """Citation resource."""


class CitationsResource(GrampsObjectsProtectedResource, CitationResourceHelper):
    """Citations resource."""
