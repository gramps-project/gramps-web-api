"""Source API resource."""

from typing import Dict

from gramps.gen.lib import Source

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import get_media_for_references, get_repositories_for_references


class SourceResourceHelper(GrampsObjectResourceHelper):
    """Source resource helper."""

    gramps_class_name = "Source"

    def object_extend(self, obj: Source, args: Dict) -> Source:
        """Extend source attributes as needed."""
        if args["extend"]:
            db = self.db
            obj.extended = {
                "media": get_media_for_references(db, obj),
                "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
                "repositories": get_repositories_for_references(db, obj),
                "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list],
            }
        return obj


class SourceResource(GrampsObjectProtectedResource, SourceResourceHelper):
    """Source resource."""


class SourcesResource(GrampsObjectsProtectedResource, SourceResourceHelper):
    """Sources resource."""
