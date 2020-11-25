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
from gramps.gen.lib import Event, Family, Person, Place, Source, Span
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


def get_event_profile_for_object(
    db_handle: DbReadBase, event: Event, base_event=None, label="span"
) -> Dict:
    """Get event profile given an Event."""
    result = {
        "type": str(event.type),
        "date": dd.display(event.date),
        "place": pd.display_event(db_handle, event),
    }
    if base_event is not None:
        result[label] = (
            Span(base_event.date, event.date).format(precision=3).strip("()")
        )
    return result


def get_event_profile_for_handle(
    db_handle: DbReadBase, handle: Handle, base_event=None, label="span"
) -> Dict:
    """Get event profile given a handle."""
    try:
        obj = db_handle.get_event_from_handle(handle)
    except HandleError:
        return {}
    return get_event_profile_for_object(db_handle, obj, base_event, label)


def get_birth_profile(db_handle: DbReadBase, person: Person) -> Dict:
    """Return best available birth information for a person."""
    event = get_birth_or_fallback(db_handle, person)
    if event is None:
        return {}, None
    return get_event_profile_for_object(db_handle, event), event


def get_death_profile(db_handle: DbReadBase, person: Person) -> Dict:
    """Return best available death information for a person."""
    event = get_death_or_fallback(db_handle, person)
    if event is None:
        return {}, None
    return get_event_profile_for_object(db_handle, event), event


def get_marriage_profile(db_handle: DbReadBase, family: Family) -> Dict:
    """Return best available marriage information for a couple."""
    event = get_marriage_or_fallback(db_handle, family)
    if event is None:
        return {}, None
    return get_event_profile_for_object(db_handle, event), event


def get_divorce_profile(db_handle: DbReadBase, family: Family) -> Dict:
    """Return best available divorce information for a couple."""
    event = get_divorce_or_fallback(db_handle, family)
    if event is None:
        return {}, None
    return get_event_profile_for_object(db_handle, event), event


def get_person_profile_for_object(
    db_handle: DbReadBase, person: Person, args: List
) -> Person:
    """Get person profile given a Person."""
    birth, birth_event = get_birth_profile(db_handle, person)
    death, death_event = get_death_profile(db_handle, person)
    if "all" in args or "age" in args:
        if birth_event is not None:
            birth["age"] = "0 days"
            if death_event is not None:
                death["age"] = (
                    Span(birth_event.date, death_event.date)
                    .format(precision=3)
                    .strip("()")
                )
    profile = {
        "handle": person.handle,
        "sex": get_sex_profile(person),
        "birth": birth,
        "death": death,
        "name_given": nd.display_given(person),
        "name_surname": person.primary_name.get_surname(),
    }
    if "all" in args or "family" in args:
        primary_parent_family_handle = person.get_main_parents_family_handle()
        profile["primary_parent_family"] = get_family_profile_for_handle(
            db_handle, primary_parent_family_handle, []
        )
        profile["other_parent_families"] = []
        for handle in person.parent_family_list:
            if handle != primary_parent_family_handle:
                profile["other_parent_families"].append(
                    get_family_profile_for_handle(db_handle, handle, [])
                )
        profile["families"] = [
            get_family_profile_for_handle(db_handle, handle, [])
            for handle in person.family_list
        ]
    if "all" in args or "events" in args:
        if "age" not in args and "all" not in args:
            birth_event = None
        profile["events"] = [
            get_event_profile_for_handle(db_handle, event_ref.ref, birth_event, "age")
            for event_ref in person.event_ref_list
        ]
    return profile


def get_person_profile_for_handle(
    db_handle: DbReadBase, handle: Handle, args: List
) -> Union[Person, Dict]:
    """Get person profile given a handle."""
    try:
        obj = db_handle.get_person_from_handle(handle)
    except HandleError:
        return {}
    return get_person_profile_for_object(db_handle, obj, args)


def get_family_profile_for_object(
    db_handle: DbReadBase, family: Family, args: List
) -> Family:
    """Get family profile given a Family."""
    marriage, marriage_event = get_marriage_profile(db_handle, family)
    divorce, divorce_event = get_divorce_profile(db_handle, family)
    if "all" in args or "span" in args:
        if marriage_event is not None:
            marriage["span"] = "0 days"
            if divorce_event is not None:
                divorce["span"] = (
                    Span(marriage_event.date, divorce_event.date)
                    .format(precision=3)
                    .strip("()")
                )
    if "all" in args or "age" in args:
        family_args = ["age"]
    else:
        family_args = []
    profile = {
        "handle": family.handle,
        "father": get_person_profile_for_handle(
            db_handle, family.father_handle, family_args
        ),
        "mother": get_person_profile_for_handle(
            db_handle, family.mother_handle, family_args
        ),
        "relationship": family.type,
        "marriage": marriage,
        "divorce": divorce,
        "children": [
            get_person_profile_for_handle(db_handle, child_ref.ref, family_args)
            for child_ref in family.child_ref_list
        ],
    }
    if "all" in args or "events" in args:
        if "span" not in args and "all" not in args:
            marriage_event = None
        profile["events"] = [
            get_event_profile_for_handle(
                db_handle, event_ref.ref, marriage_event, label="span"
            )
            for event_ref in family.event_ref_list
        ]
    return profile


def get_family_profile_for_handle(
    db_handle: DbReadBase, handle: Handle, args: List
) -> Union[Family, Dict]:
    """Get family profile given a handle."""
    try:
        obj = db_handle.get_family_from_handle(handle)
    except HandleError:
        return {}
    return get_family_profile_for_object(db_handle, obj, args)


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
