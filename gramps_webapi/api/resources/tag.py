"""Tag API resource."""

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)


class TagResourceHelper(GrampsObjectResourceHelper):
    """Tag resource helper."""

    gramps_class_name = "Tag"


class TagResource(GrampsObjectProtectedResource, TagResourceHelper):
    """Tag resource."""


class TagsResource(GrampsObjectsProtectedResource, TagResourceHelper):
    """Tags resource."""
