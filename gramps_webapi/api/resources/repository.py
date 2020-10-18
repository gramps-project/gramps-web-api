"""Repository API resource."""

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)


class RepositoryResourceHelper(GrampsObjectResourceHelper):
    """Repository resource helper."""

    gramps_class_name = "Repository"


class RepositoryResource(GrampsObjectProtectedResource, RepositoryResourceHelper):
    """Repository resource."""


class RepositoriesResource(GrampsObjectsProtectedResource, RepositoryResourceHelper):
    """Repositories resource."""
