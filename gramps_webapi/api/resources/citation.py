"""Citation API resource."""

from typing import Dict

from gramps.gen.lib import Citation

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import get_extended_attributes, get_source_by_handle


class CitationResourceHelper(GrampsObjectResourceHelper):
    """Citation resource helper."""

    gramps_class_name = "Citation"

    def object_extend(self, obj: Citation, args: Dict) -> Citation:
        """Extend citation attributes as needed."""
        if "extend" in args:
            db_handle = self.db_handle
            obj.extended = get_extended_attributes(db_handle, obj, args)
            if (
                "all" in args["extend"]
                or "" in args["extend"]
                or "source" in args["extend"]
            ):
                obj.extended["source"] = get_source_by_handle(
                    db_handle, obj.source_handle, args
                )
        return obj


class CitationResource(GrampsObjectProtectedResource, CitationResourceHelper):
    """Citation resource."""


class CitationsResource(GrampsObjectsProtectedResource, CitationResourceHelper):
    """Citations resource."""
