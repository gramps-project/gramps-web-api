"""Media API resource."""

from typing import Dict

from gramps.gen.lib import Media

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import get_extended_attributes


class MediaObjectResourceHelper(GrampsObjectResourceHelper):
    """Media resource helper."""

    gramps_class_name = "Media"

    def object_extend(self, obj: Media, args: Dict) -> Media:
        """Extend media attributes as needed."""
        if args["extend"]:
            db_handle = self.db_handle
            obj.extended = get_extended_attributes(db_handle, obj)
        return obj


class MediaObjectResource(GrampsObjectProtectedResource, MediaObjectResourceHelper):
    """Media object resource."""


class MediaObjectsResource(GrampsObjectsProtectedResource, MediaObjectResourceHelper):
    """Media objects resource."""
