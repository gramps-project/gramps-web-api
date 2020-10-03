"""Tag API resource."""

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)


class TagResourceHelper(GrampsObjectResourceHelper):
    """Tag resource helper."""

    gramps_class_name = "Tag"

    def object_denormalize(self, obj):
        """Denormalize note attributes if needed."""
        return obj

    
class TagResource(GrampsObjectProtectedResource, TagResourceHelper):
    """Tag resource."""


class TagsResource(GrampsObjectsProtectedResource, TagResourceHelper):
    """Tags resource."""
