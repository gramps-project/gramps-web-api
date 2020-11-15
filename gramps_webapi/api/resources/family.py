"""Family API resource."""

from typing import Dict

from gramps.gen.lib import Family

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import (
    get_extended_attributes,
    get_family_profile_for_object,
    get_person_by_handle,
)


class FamilyResourceHelper(GrampsObjectResourceHelper):
    """Family resource helper."""

    gramps_class_name = "Family"

    def object_extend(self, obj: Family, args: Dict) -> Family:
        """Extend family attributes as needed."""
        db_handle = self.db_handle
        if "profile" in args:
            if "all" in args["profile"] or "families" in args["profile"]:
                if "all" in args["profile"] or "events" in args["profile"]:
                    with_events = True
                else:
                    with_events = False
                obj.profile = get_family_profile_for_object(
                    db_handle, obj, with_events=with_events
                )
        if "extend" in args:
            obj.extended = get_extended_attributes(db_handle, obj, args)
            if "all" in args["extend"] or "father_handle" in args["extend"]:
                obj.extended["father"] = get_person_by_handle(
                    db_handle, obj.father_handle
                )
            if "all" in args["extend"] or "mother_handle" in args["extend"]:
                obj.extended["mother"] = get_person_by_handle(
                    db_handle, obj.mother_handle
                )
        return obj


class FamilyResource(GrampsObjectProtectedResource, FamilyResourceHelper):
    """Family resource."""


class FamiliesResource(GrampsObjectsProtectedResource, FamilyResourceHelper):
    """Families resource."""
