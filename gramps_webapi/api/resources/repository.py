"""Repository API resource."""

from typing import Dict

from gramps.gen.lib import Repository

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import get_extended_attributes


class RepositoryResourceHelper(GrampsObjectResourceHelper):
    """Repository resource helper."""

    gramps_class_name = "Repository"

    def object_extend(self, obj: Repository, args: Dict) -> Repository:
        """Extend repository attributes as needed."""
        if args["extend"]:
            db_handle = self.db_handle
            obj.extended = get_extended_attributes(db_handle, obj)
        return obj


class RepositoryResource(GrampsObjectProtectedResource, RepositoryResourceHelper):
    """Tag resource."""


class RepositoriesResource(GrampsObjectsProtectedResource, RepositoryResourceHelper):
    """Repositories resource."""
