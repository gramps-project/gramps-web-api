"""Citation API resource."""

from gramps.gen.lib import Citation

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import get_media_for_references, get_source_by_handle


class CitationResourceHelper(GrampsObjectResourceHelper):
    """Citation resource helper."""

    gramps_class_name = "Citation"

    def object_extend(self, obj, args) -> Citation:
        """Extend citation attributes as needed."""
        if args["extend"]:
            db = self.db
            obj.extended = {
                "media": get_media_for_references(db, obj),
                "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
                "source": get_source_by_handle(db, obj.source_handle),
                "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list],
            }
        return obj


class CitationResource(GrampsObjectProtectedResource, CitationResourceHelper):
    """Citation resource."""


class CitationsResource(GrampsObjectsProtectedResource, CitationResourceHelper):
    """Citations resource."""
