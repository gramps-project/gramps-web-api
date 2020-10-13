"""Tag API resource."""

from typing import Dict

from gramps.gen.lib import Tag

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)


class TagResourceHelper(GrampsObjectResourceHelper):
    """Tag resource helper."""

    gramps_class_name = "Tag"

    def object_extend(self, obj: Tag, args: Dict) -> Tag:
        """Extend tag attributes as needed."""
        return obj


class TagResource(GrampsObjectProtectedResource, TagResourceHelper):
    """Tag resource."""


class TagsResource(GrampsObjectsProtectedResource, TagResourceHelper):
    """Tags resource."""
