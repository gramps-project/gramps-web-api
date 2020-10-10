"""Place API resource."""

from typing import Dict

from gramps.gen.lib import Place

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import get_media_for_references


class PlaceResourceHelper(GrampsObjectResourceHelper):
    """Place resource helper."""

    gramps_class_name = "Place"

    def object_extend(self, obj: Place, args: Dict) -> Place:
        """Extend place attributes as needed."""
        if args["extend"]:
            db = self.db
            obj.extended = {
                "citations": [
                    db.get_citation_from_handle(handle) for handle in obj.citation_list
                ],
                "media": get_media_for_references(db, obj),
                "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
                "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list],
            }
        return obj


class PlaceResource(GrampsObjectProtectedResource, PlaceResourceHelper):
    """Place resource."""


class PlacesResource(GrampsObjectsProtectedResource, PlaceResourceHelper):
    """Places resource."""
