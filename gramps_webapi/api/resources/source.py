"""Source API resource."""

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)


class SourceResourceHelper(GrampsObjectResourceHelper):
    """Source resource helper."""

    gramps_class_name = "Source"

    def object_denormalize(self, obj):
        """Denormalize source attributes if needed."""
        return obj

    
class SourceResource(GrampsObjectProtectedResource, SourceResourceHelper):
    """Source resource."""


class SourcesResource(GrampsObjectsProtectedResource, SourceResourceHelper):
    """Sources resource."""
