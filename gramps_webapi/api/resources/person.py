"""Person API resource."""

from typing import Dict

from gramps.gen.lib import Person

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import (
    get_extended_attributes,
    get_family_by_handle,
    get_person_profile_for_object,
)


class PersonResourceHelper(GrampsObjectResourceHelper):
    """Person resource helper."""

    gramps_class_name = "Person"

    def object_extend(self, obj: Person, args: Dict) -> Person:
        """Extend person attributes as needed."""
        db_handle = self.db_handle
        if "profile" in args:
            if "all" in args["profile"] or "families" in args["profile"]:
                with_family = True
            else:
                with_family = False
            if "all" in args["profile"] or "events" in args["profile"]:
                with_events = True
            else:
                with_events = False
            obj.profile = get_person_profile_for_object(
                db_handle, obj, with_family=with_family, with_events=with_events
            )
        if "extend" in args:
            obj.extended = get_extended_attributes(db_handle, obj, args)
            if "all" in args["extend"] or "families" in args["extend"]:
                obj.extended["families"] = [
                    get_family_by_handle(db_handle, handle)
                    for handle in obj.family_list
                ]
            if "all" in args["extend"] or "parent_families" in args["extend"]:
                obj.extended["parent_families"] = [
                    get_family_by_handle(db_handle, handle)
                    for handle in obj.parent_family_list
                ]
            if "all" in args["extend"] or "primary_parent_family" in args["extend"]:
                obj.extended["primary_parent_family"] = get_family_by_handle(
                    db_handle, obj.get_main_parents_family_handle()
                )
        return obj


class PersonResource(GrampsObjectProtectedResource, PersonResourceHelper):
    """Person resource."""


class PeopleResource(GrampsObjectsProtectedResource, PersonResourceHelper):
    """People resource."""
