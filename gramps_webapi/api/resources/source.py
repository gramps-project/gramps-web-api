"""Source API resource."""

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)


class SourceResourceHelper(GrampsObjectResourceHelper):
    """Source resource helper."""

    gramps_class_name = "Source"


class SourceResource(GrampsObjectProtectedResource, SourceResourceHelper):
    """Source resource."""


class SourcesResource(GrampsObjectsProtectedResource, SourceResourceHelper):
    """Sources resource."""
