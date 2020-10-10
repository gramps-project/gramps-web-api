"""Repository API resource."""

from typing import Dict

from gramps.gen.lib import Repository

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)


class RepositoryResourceHelper(GrampsObjectResourceHelper):
    """Repository resource helper."""

    gramps_class_name = "Repository"

    def object_extend(self, obj: Repository, args: Dict) -> Repository:
        """Extend repository attributes as needed."""
        if args["extend"]:
            db = self.db
            obj.extended = {
                "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
                "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list],
            }
        return obj


class RepositoryResource(GrampsObjectProtectedResource, RepositoryResourceHelper):
    """Tag resource."""


class RepositoriesResource(GrampsObjectsProtectedResource, RepositoryResourceHelper):
    """Repositories resource."""
