"""Media API resource."""

from .base import (GrampsObjectProtectedResource, GrampsObjectResourceHelper,
                   GrampsObjectsProtectedResource)


class MediaObjectResourceHelper(GrampsObjectResourceHelper):
    """Media resource helper."""

    gramps_class_name = "Media"

    def object_extend(self, obj):
        """Extend media attributes as needed."""
        if self.extend_object:
            db = self.db
            obj.extended = {
                "citations": [
                    db.get_citation_from_handle(handle) for handle in obj.citation_list
                ],
                "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
                "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list],
            }
        return obj


class MediaObjectResource(GrampsObjectProtectedResource, MediaObjectResourceHelper):
    """Media object resource."""


class MediaObjectsResource(GrampsObjectsProtectedResource, MediaObjectResourceHelper):
    """Media objects resource."""
