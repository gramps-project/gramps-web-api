"""Media API resource."""

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)


class MediaObjectResourceHelper(GrampsObjectResourceHelper):
    """Media resource helper."""

    gramps_class_name = "Media"

    def object_denormalize(self, obj):
        """Denormalize media attributes if needed."""
        return obj

    
class MediaObjectResource(GrampsObjectProtectedResource, MediaObjectResourceHelper):
    """Media object resource."""


class MediaObjectsResource(GrampsObjectsProtectedResource, MediaObjectResourceHelper):
    """Media objects resource."""
