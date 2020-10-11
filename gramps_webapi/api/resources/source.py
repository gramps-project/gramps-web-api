"""Source API resource."""

from typing import Dict

from gramps.gen.lib import Source

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import get_extended_attributes


class SourceResourceHelper(GrampsObjectResourceHelper):
    """Source resource helper."""

    gramps_class_name = "Source"

    def object_extend(self, obj: Source, args: Dict) -> Source:
        """Extend source attributes as needed."""
        if args["extend"]:
            db_handle = self.db_handle
            obj.extended = get_extended_attributes(db_handle, obj)
        return obj


class SourceResource(GrampsObjectProtectedResource, SourceResourceHelper):
    """Source resource."""


class SourcesResource(GrampsObjectsProtectedResource, SourceResourceHelper):
    """Sources resource."""
