"""Family API resource."""

from .base import (GrampsObjectProtectedResource, GrampsObjectResourceHelper,
                   GrampsObjectsProtectedResource)


class FamilyResourceHelper(GrampsObjectResourceHelper):
    """Family resource helper."""

    gramps_class_name = "Family"

    def object_denormalize(self, obj):
        """Denormalize family attributes if needed."""
        return obj


class FamilyResource(GrampsObjectProtectedResource, FamilyResourceHelper):
    """Family resource."""


class FamiliesResource(GrampsObjectsProtectedResource, FamilyResourceHelper):
    """Families resource."""
