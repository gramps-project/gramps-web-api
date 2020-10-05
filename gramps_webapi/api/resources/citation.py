"""Citation API resource."""

from .base import (GrampsObjectProtectedResource, GrampsObjectResourceHelper,
                   GrampsObjectsProtectedResource)


class CitationResourceHelper(GrampsObjectResourceHelper):
    """Citation resource helper."""

    gramps_class_name = "Citation"

    def object_denormalize(self, obj):
        """Denormalize citation attributes if needed."""
        return obj


class CitationResource(GrampsObjectProtectedResource, CitationResourceHelper):
    """Citation resource."""


class CitationsResource(GrampsObjectsProtectedResource, CitationResourceHelper):
    """Citations resource."""
