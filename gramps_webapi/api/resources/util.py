#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
# Copyright (C) 2020      Christopher Horn
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Gramps utility functions."""

from typing import Dict, List, Optional, Union

from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.db.base import DbReadBase
from gramps.gen.display.name import NameDisplay
from gramps.gen.display.place import PlaceDisplay
from gramps.gen.errors import HandleError
from gramps.gen.lib import Event, Family, Person, Place, Source
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from gramps.gen.utils.db import (
    get_birth_or_fallback,
    get_death_or_fallback,
    get_divorce_or_fallback,
    get_marriage_or_fallback,
)

from ...const import SEX_FEMALE, SEX_MALE, SEX_UNKNOWN
from ...types import Handle

nd = NameDisplay()
pd = PlaceDisplay()
dd = GRAMPS_LOCALE.date_displayer


def get_person_by_handle(db_handle: DbReadBase, handle: Handle) -> Union[Person, Dict]:
    """Safe get person by handle."""
    try:
        return db_handle.get_person_from_handle(handle)
    except HandleError:
        return {}


def get_place_by_handle(db_handle: DbReadBase, handle: Handle) -> Union[Place, Dict]:
    """Safe get place by handle."""
    try:
        return db_handle.get_place_from_handle(handle)
    except HandleError:
        return {}


def get_family_by_handle(
    db_handle: DbReadBase, handle: Handle, args: Optional[Dict] = None
) -> Union[Family, Dict]:
    """Get a family and optional extended attributes."""
    try:
        obj = db_handle.get_family_from_handle(handle)
    except HandleError:
        return {}
    args = args or {}
    if "extend" in args:
        obj.extended = get_extended_attributes(db_handle, obj, args)
        if "all" in args["extend"] or "father" in args["extend"]:
            obj.extended["father"] = get_person_by_handle(db_handle, obj.father_handle)
        if "all" in args["extend"] or "mother" in args["extend"]:
            obj.extended["mother"] = get_person_by_handle(db_handle, obj.mother_handle)
    return obj


def get_source_by_handle(
    db_handle: DbReadBase, handle: Handle, args: Optional[Dict] = None
) -> Source:
    """Get a source and optional extended attributes."""
    args = args or {}
    obj = db_handle.get_source_from_handle(handle)
    if "extend" in args:
        obj.extended = get_extended_attributes(db_handle, obj, args)
    return obj


def get_sex_profile(person: Person) -> str:
    """Get character substitution for enumerated sex."""
    if person.gender == person.MALE:
        return SEX_MALE
    if person.gender == person.FEMALE:
        return SEX_FEMALE
    return SEX_UNKNOWN


def get_event_profile_for_object(db_handle: DbReadBase, event: Event) -> Dict:
    """Get event profile given an Event."""
    return {
        "type": str(event.type),
        "date": dd.display(event.date),
        "place": pd.display_event(db_handle, event),
    }


def get_event_profile_for_handle(db_handle: DbReadBase, handle: Handle) -> Dict:
    """Get event profile given a handle."""
    try:
        obj = db_handle.get_event_from_handle(handle)
    except HandleError:
        return {}
    return get_event_profile_for_object(db_handle, obj)


def get_birth_profile(db_handle: DbReadBase, person: Person) -> Dict:
    """Return best available birth information for a person."""
    event = get_birth_or_fallback(db_handle, person)
    if event is None:
        return {}
    return get_event_profile_for_object(db_handle, event)


def get_death_profile(db_handle: DbReadBase, person: Person) -> Dict:
    """Return best available death information for a person."""
    event = get_death_or_fallback(db_handle, person)
    if event is None:
        return {}
    return get_event_profile_for_object(db_handle, event)


def get_marriage_profile(db_handle: DbReadBase, family: Family) -> Dict:
    """Return best available marriage information for a couple."""
    event = get_marriage_or_fallback(db_handle, family)
    if event is None:
        return {}
    return get_event_profile_for_object(db_handle, event)


def get_divorce_profile(db_handle: DbReadBase, family: Family) -> Dict:
    """Return best available divorce information for a couple."""
    event = get_divorce_or_fallback(db_handle, family)
    if event is None:
        return {}
    return get_event_profile_for_object(db_handle, event)


def get_person_profile_for_object(
    db_handle: DbReadBase,
    person: Person,
    with_family: bool = True,
    with_events: bool = True,
) -> Person:
    """Get person profile given a Person."""
    profile = {
        "handle": person.handle,
        "sex": get_sex_profile(person),
        "birth": get_birth_profile(db_handle, person),
        "death": get_death_profile(db_handle, person),
        "name_given": nd.display_given(person),
        "name_surname": person.primary_name.get_surname(),
    }
    if with_family:
        primary_parent_family_handle = person.get_main_parents_family_handle()
        profile["primary_parent_family"] = get_family_profile_for_handle(
            db_handle, primary_parent_family_handle
        )
        profile["other_parent_families"] = []
        for handle in person.parent_family_list:
            if handle != primary_parent_family_handle:
                profile["other_parent_families"].append(
                    get_family_profile_for_handle(db_handle, handle)
                )
        profile["families"] = [
            get_family_profile_for_handle(db_handle, handle)
            for handle in person.family_list
        ]
    if with_events:
        profile["events"] = [
            get_event_profile_for_handle(db_handle, event_ref.ref)
            for event_ref in person.event_ref_list
        ]
    return profile


def get_person_profile_for_handle(
    db_handle: DbReadBase,
    handle: Handle,
    with_family: bool = True,
    with_events: bool = True,
) -> Union[Person, Dict]:
    """Get person profile given a handle."""
    try:
        obj = db_handle.get_person_from_handle(handle)
    except HandleError:
        return {}
    return get_person_profile_for_object(db_handle, obj, with_family, with_events)


def get_family_profile_for_object(
    db_handle: DbReadBase, family: Family, with_events: bool = True
) -> Family:
    """Get family profile given a Family."""
    profile = {
        "handle": family.handle,
        "father": get_person_profile_for_handle(
            db_handle, family.father_handle, with_family=False, with_events=False
        ),
        "mother": get_person_profile_for_handle(
            db_handle, family.mother_handle, with_family=False, with_events=False
        ),
        "relationship": family.type,
        "marriage": get_marriage_profile(db_handle, family),
        "divorce": get_divorce_profile(db_handle, family),
        "children": [
            get_person_profile_for_handle(
                db_handle, child_ref.ref, with_family=False, with_events=False
            )
            for child_ref in family.child_ref_list
        ],
    }
    if with_events:
        profile["events"] = [
            get_event_profile_for_handle(db_handle, event_ref.ref)
            for event_ref in family.event_ref_list
        ]
    return profile


def get_family_profile_for_handle(
    db_handle: DbReadBase, handle: Handle, with_events: bool = True
) -> Union[Family, Dict]:
    """Get family profile given a handle."""
    try:
        obj = db_handle.get_family_from_handle(handle)
    except HandleError:
        return {}
    return get_family_profile_for_object(db_handle, obj, with_events)


def get_extended_attributes(
    db_handle: DbReadBase, obj: GrampsObject, args: Optional[Dict] = None
) -> Dict:
    """Get extended attributes for a GrampsObject."""
    args = args or {}
    result = {}
    do_all = False
    if "all" in args["extend"]:
        do_all = True
    if (do_all or "child_ref_list" in args["extend"]) and hasattr(
        obj, "child_ref_list"
    ):
        result["children"] = [
            db_handle.get_person_from_handle(child_ref.ref)
            for child_ref in obj.child_ref_list
        ]
    if (do_all or "citation_list" in args["extend"]) and hasattr(obj, "citation_list"):
        result["citations"] = [
            db_handle.get_citation_from_handle(handle) for handle in obj.citation_list
        ]
    if (do_all or "event_ref_list" in args["extend"]) and hasattr(
        obj, "event_ref_list"
    ):
        result["events"] = [
            db_handle.get_event_from_handle(event_ref.ref)
            for event_ref in obj.event_ref_list
        ]
    if (do_all or "media_list" in args["extend"]) and hasattr(obj, "media_list"):
        result["media"] = [
            db_handle.get_media_from_handle(media_ref.ref)
            for media_ref in obj.media_list
        ]
    if (do_all or "note_list" in args["extend"]) and hasattr(obj, "note_list"):
        result["notes"] = [
            db_handle.get_note_from_handle(handle) for handle in obj.note_list
        ]
    if (do_all or "person_ref_list" in args["extend"]) and hasattr(
        obj, "person_ref_list"
    ):
        result["people"] = [
            db_handle.get_person_from_handle(person_ref.ref)
            for person_ref in obj.person_ref_list
        ]
    if (do_all or "reporef_list" in args["extend"]) and hasattr(obj, "reporef_list"):
        result["repositories"] = [
            db_handle.get_repository_from_handle(repo_ref.ref)
            for repo_ref in obj.reporef_list
        ]
    if (do_all or "tag_list" in args["extend"]) and hasattr(obj, "tag_list"):
        result["tags"] = [
            db_handle.get_tag_from_handle(handle) for handle in obj.tag_list
        ]
    if (do_all or "backlinks" in args["extend"]) and hasattr(obj, "backlinks"):
        result["backlinks"] = {}
        for class_name, backlinks in obj.backlinks.items():
            result["backlinks"][class_name] = [
                db_handle.method("get_%s_from_handle", class_name.upper())(handle)
                for handle in backlinks
            ]
    return result


def get_backlinks(db_handle: DbReadBase, handle: Handle) -> Dict[str, List[Handle]]:
    """Get backlinks to a handle.

    Will return a dictionary of the form
    `{'object_type': ['handle1', 'handle2', ...], ...}`
    """
    backlinks = {}
    for obj_type, target_handle in db_handle.find_backlink_handles(handle):
        key = obj_type.lower()
        if key not in backlinks:
            backlinks[key] = []
        backlinks[key].append(target_handle)
    return backlinks
