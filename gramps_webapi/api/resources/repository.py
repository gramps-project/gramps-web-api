"""Repository API resource."""

from .base import (GrampsObjectProtectedResource, GrampsObjectResourceHelper,
                   GrampsObjectsProtectedResource)


class RepositoryResourceHelper(GrampsObjectResourceHelper):
    """Repository resource helper."""

    gramps_class_name = "Repository"

    def object_denormalize(self, obj):
        """Denormalize repository attributes if needed."""
        return obj


class RepositoryResource(GrampsObjectProtectedResource, RepositoryResourceHelper):
    """Tag resource."""


class RepositoriesResource(GrampsObjectsProtectedResource, RepositoryResourceHelper):
    """Repositories resource."""
