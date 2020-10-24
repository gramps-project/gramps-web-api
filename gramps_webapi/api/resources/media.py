"""Media API resource."""

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)


class MediaObjectResourceHelper(GrampsObjectResourceHelper):
    """Media resource helper."""

    gramps_class_name = "Media"


class MediaObjectResource(GrampsObjectProtectedResource, MediaObjectResourceHelper):
    """Media object resource."""


class MediaObjectsResource(GrampsObjectsProtectedResource, MediaObjectResourceHelper):
    """Media objects resource."""
