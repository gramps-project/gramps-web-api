#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2025 David Straub
# Copyright (C) 2020      Christopher Horn
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Gramps utility functions."""

from __future__ import annotations

import copy
import gzip
import logging
import os
import re
from hashlib import sha256
from http import HTTPStatus
from typing import Any, Literal, Optional, Union, cast

import gramps
import gramps.gen.lib
import jsonschema
from celery import Task
from flask import Response, current_app, request
from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.const import PLUGINS_DIR, USER_PLUGINS
from gramps.gen.db import KEY_TO_CLASS_MAP, DbTxn
from gramps.gen.db.base import DbReadBase, DbWriteBase
from gramps.gen.db.dbconst import TXNADD, TXNDEL, TXNUPD
from gramps.gen.display.name import NameDisplay
from gramps.gen.display.place import PlaceDisplay
from gramps.gen.errors import HandleError
from gramps.gen.lib import (
    Citation,
    Event,
    EventRoleType,
    Family,
    Media,
    Person,
    Place,
    PlaceType,
    Source,
    Span,
)
from gramps.gen.lib.genderstats import GenderStats

# from gramps.gen.lib.serialize import to_json
from gramps.gen.lib.json_utils import (
    object_to_dict,
    object_to_string,
    remove_object,
    string_to_object,
)
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from gramps.gen.plug import BasePluginManager
from gramps.gen.relationship import get_relationship_calculator
from gramps.gen.soundex import soundex
from gramps.gen.user import User
from gramps.gen.utils.db import (
    get_birth_or_fallback,
    get_death_or_fallback,
    get_divorce_or_fallback,
    get_marriage_or_fallback,
)
from gramps.gen.utils.grampslocale import GrampsLocale
from gramps.gen.utils.id import create_id
from gramps.gen.utils.place import conv_lat_lon
from gramps.gen.display.name import displayer as default_name_displayer

import gramps_gedcom7

from ...const import DISABLED_IMPORTERS, SEX_FEMALE, SEX_MALE, SEX_OTHER, SEX_UNKNOWN
from ...types import FilenameOrPath, Handle, TransactionJson
from .fast_sqlite import FastSQLite
from ..media import get_media_handler
from ..util import (
    UserTaskProgress,
    abort_with_message,
    get_db_handle,
    get_tree_from_jwt,
)

pd = PlaceDisplay()
_ = glocale.translation.gettext
_LOG = logging.getLogger(__name__)


def get_person_by_handle(db_handle: DbReadBase, handle: Handle) -> Union[Person, dict]:
    """Safe get person by handle."""
    try:
        person = db_handle.get_person_from_handle(handle)
        if person is None:
            return {}
        return person
    except HandleError:
        return {}


def get_place_by_handle(db_handle: DbReadBase, handle: Handle) -> Union[Place, dict]:
    """Safe get place by handle."""
    try:
        place = db_handle.get_place_from_handle(handle)
        if place is None:
            return {}
        return place
    except HandleError:
        return {}


def get_family_by_handle(
    db_handle: DbReadBase, handle: Handle, args: Optional[dict] = None
) -> Union[Family, dict]:
    """Get a family and optional extended attributes."""
    try:
        obj = db_handle.get_family_from_handle(handle)
        if obj is None:
            return {}
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
    db_handle: DbReadBase, handle: Handle, args: Optional[dict] = None
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
    if person.gender == person.OTHER:
        return SEX_OTHER
    return SEX_UNKNOWN


def get_family_name_localized(
    family: Family, db_handle: DbReadBase, locale: GrampsLocale = glocale
) -> str:
    """
    Get a localized family name for display.

    This is a locale-aware version of gramps.gen.utils.db.family_name()
    that properly translates the "and" connector based on the requested locale.

    Args:
        family: The Family object
        db_handle: Database handle
        locale: The locale to use for translation (default: server locale)

    Returns:
        A formatted family name string with proper locale translation
    """
    father = None
    father_handle = family.get_father_handle()
    if father_handle:
        father = db_handle.get_person_from_handle(father_handle)

    mother = None
    mother_handle = family.get_mother_handle()
    if mother_handle:
        mother = db_handle.get_person_from_handle(mother_handle)

    if father and mother:
        fname = default_name_displayer.display(father)
        mname = default_name_displayer.display(mother)
        # Use the provided locale for translation instead of server default
        return locale.translation.gettext("%(father)s and %(mother)s") % {
            "father": fname,
            "mother": mname,
        }
    if father:
        return default_name_displayer.display(father)
    if mother:
        return default_name_displayer.display(mother)
    return locale.translation.gettext("unknown")


def get_participant_from_event_localized(
    db_handle: DbReadBase,
    event_handle: Handle,
    locale: GrampsLocale = glocale,
    all_: bool = False,
) -> str:
    """
    Get the participant name(s) from an event with proper locale translation.

    This is a locale-aware version of gramps.gen.utils.db.get_participant_from_event()
    that properly translates family names based on the requested locale.

    Args:
        db_handle: Database handle
        event_handle: Handle of the event
        locale: The locale to use for translation (default: server locale)
        all_: If True, return all participants; if False, add ellipsis for multiple

    Returns:
        A formatted string of participant name(s)
    """
    participant = ""
    ellipses = False
    result_list = list(
        db_handle.find_backlink_handles(
            event_handle, include_classes=["Person", "Family"]
        )
    )

    # obtain handles without duplicates
    people = set([x[1] for x in result_list if x[0] == "Person"])
    families = set([x[1] for x in result_list if x[0] == "Family"])

    for person_handle in people:
        person = db_handle.get_person_from_handle(person_handle)
        if not person:
            continue
        for event_ref in person.get_event_ref_list():
            if event_handle == event_ref.ref and event_ref.get_role().is_primary():
                if participant:
                    if all_:
                        participant += f", {default_name_displayer.display(person)}"
                    else:
                        ellipses = True
                else:
                    participant = default_name_displayer.display(person)
                break
        if ellipses:
            break

    if ellipses:
        return locale.translation.gettext("%s, ...") % participant

    for family_handle in families:
        family = db_handle.get_family_from_handle(family_handle)
        for event_ref in family.get_event_ref_list():
            if event_handle == event_ref.ref and event_ref.get_role().is_family():
                if participant:
                    if all_:
                        participant += (
                            f", {get_family_name_localized(family, db_handle, locale)}"
                        )
                    else:
                        ellipses = True
                else:
                    participant = get_family_name_localized(family, db_handle, locale)
                break
        if ellipses:
            break

    if ellipses:
        return locale.translation.gettext("%s, ...") % participant
    return participant


def get_event_participants_for_handle(
    db_handle: DbReadBase,
    handle: Handle,
    locale: GrampsLocale = glocale,
) -> dict[Literal["people", "families"], list[tuple[EventRoleType, Person | Family]]]:
    """Get event participants given a handle."""
    result: dict[
        Literal["people", "families"], list[tuple[EventRoleType, Person | Family]]
    ] = {
        "people": [],
        "families": [],
    }
    seen = set()  # to avoid duplicates
    for class_name, backref_handle in db_handle.find_backlink_handles(
        handle, include_classes=["Person", "Family"]
    ):
        if backref_handle in seen:
            continue
        seen.add(backref_handle)
        if class_name == "Person":
            try:
                person = db_handle.get_person_from_handle(backref_handle)
            except HandleError:
                continue
            if not person:
                continue
            for event_ref in person.get_event_ref_list():
                if handle == event_ref.ref:
                    result["people"].append(
                        (
                            event_ref.get_role(),
                            person,
                        )
                    )
        elif class_name == "Family":
            try:
                family = db_handle.get_family_from_handle(backref_handle)
            except HandleError:
                continue
            if not family:
                continue
            for event_ref in family.get_event_ref_list():
                if handle == event_ref.ref:
                    result["families"].append(
                        (
                            event_ref.get_role(),
                            family,
                        )
                    )
    return result


def get_event_participants_profile_for_handle(
    db_handle: DbReadBase,
    handle: Handle,
    locale: GrampsLocale = glocale,
    name_format: Optional[str] = None,
) -> dict:
    """Get event participants given a handle."""
    event_participants = get_event_participants_for_handle(
        db_handle=db_handle,
        handle=handle,
        locale=locale,
    )
    result: dict[str, list[dict[str, Any]]] = {"people": [], "families": []}

    for role, person in event_participants["people"]:
        person_profile = get_person_profile_for_object(
            db_handle,
            cast(Person, person),
            args=[],
            locale=locale,
            name_format=name_format,
        )
        role_str = locale.translation.sgettext(role.xml_str())
        result["people"].append({"role": role_str, "person": person_profile})
    for role, family in event_participants["families"]:
        person_profile = get_family_profile_for_object(
            db_handle,
            cast(Family, family),
            args=[],
            locale=locale,
            name_format=name_format,
        )
        role_str = locale.translation.sgettext(role.xml_str())
        result["families"].append({"role": role_str, "family": person_profile})
    return result


def get_event_summary_from_object(
    db_handle: DbReadBase, event: Event, locale: GrampsLocale = glocale
):
    """Get a summary of an Event."""
    handle = event.get_handle()
    try:
        participant = get_participant_from_event_localized(db_handle, handle, locale)
    except HandleError:
        # Bad handle in database - return event type only
        participant = ""
    event_type = locale.translation.sgettext(event.type.xml_str())
    if not participant:
        return event_type
    return f"{event_type} - {participant}"


def get_event_profile_for_object(
    db_handle: DbReadBase,
    event: Event,
    args: list[str],
    base_event: Union[Event, None] = None,
    label: str = "span",
    locale: GrampsLocale = glocale,
    role: Optional[str] = None,
    name_format: Optional[str] = None,
    precision: int = 3,
) -> dict:
    """Get event profile given an Event."""
    result = {
        "type": locale.translation.sgettext(event.type.xml_str()),
        "date": locale.date_displayer.display(event.date),
        "place": pd.display_event(db_handle, event),
        "place_name": get_place_name_for_event(db_handle, event),
        "summary": get_event_summary_from_object(db_handle, event, locale=locale),
    }
    if role is not None:
        result["role"] = role
    if "all" in args or "participants" in args:
        result["participants"] = get_event_participants_profile_for_handle(
            db_handle,
            event.handle,
            locale=locale,
            name_format=name_format,
        )
    if "all" in args or "ratings" in args:
        count, confidence = get_rating(db_handle, event)
        result["citations"] = count
        result["confidence"] = confidence
    if base_event is not None:
        result[label] = (
            Span(base_event.date, event.date)
            .format(precision=precision, dlocale=locale)
            .strip("()")
        )
    return result


def get_place_name_for_event(db_handle: DbReadBase, event: Event) -> str:
    """Get place name for an event."""
    place_handle = event.get_place_handle()
    if not place_handle:
        return ""
    try:
        place: Place = db_handle.get_place_from_handle(place_handle)
    except HandleError:
        return ""
    if not place:
        return ""
    place_name = place.get_name()
    if not place_name:
        return ""
    return place_name.value


def get_event_profile_for_handle(
    db_handle: DbReadBase,
    handle: Handle,
    args: list,
    base_event: Union[Event, None] = None,
    label: str = "span",
    locale: GrampsLocale = glocale,
    role: Optional[str] = None,
    name_format: Optional[str] = None,
    precision: int = 3,
) -> dict:
    """Get event profile given a handle."""
    try:
        obj = db_handle.get_event_from_handle(handle)
        if obj is None:
            return {}
    except HandleError:
        return {}
    return get_event_profile_for_object(
        db_handle,
        obj,
        args=args,
        base_event=base_event,
        label=label,
        locale=locale,
        role=role,
        name_format=name_format,
        precision=precision,
    )


def get_birth_profile(
    db_handle: DbReadBase,
    person: Person,
    args: Union[list, None] = None,
    locale: GrampsLocale = glocale,
    name_format: str | None = None,
) -> tuple[dict, Union[Event, None]]:
    """Return best available birth information for a person."""
    try:
        event = get_birth_or_fallback(db_handle, person)
    except HandleError as exc:
        _LOG.warning("Broken event reference for person %s: %s", person.handle, exc)
        return {}, None
    if event is None:
        return {}, None
    args = args or []
    return (
        get_event_profile_for_object(
            db_handle, event, args=args, locale=locale, name_format=name_format
        ),
        event,
    )


def get_death_profile(
    db_handle: DbReadBase,
    person: Person,
    args: Union[list, None] = None,
    locale: GrampsLocale = glocale,
    name_format: str | None = None,
) -> tuple[dict, Union[Event, None]]:
    """Return best available death information for a person."""
    try:
        event = get_death_or_fallback(db_handle, person)
    except HandleError as exc:
        _LOG.warning("Broken event reference for person %s: %s", person.handle, exc)
        return {}, None
    if event is None:
        return {}, None
    args = args or []
    return (
        get_event_profile_for_object(
            db_handle, event, args=args, locale=locale, name_format=name_format
        ),
        event,
    )


def get_marriage_profile(
    db_handle: DbReadBase,
    family: Family,
    args: Union[list, None] = None,
    locale: GrampsLocale = glocale,
    name_format: str | None = None,
) -> tuple[dict, Union[Event, None]]:
    """Return best available marriage information for a couple."""
    event = get_marriage_or_fallback(db_handle, family)
    if event is None:
        return {}, None
    args = args or []
    return (
        get_event_profile_for_object(
            db_handle, event, args=args, locale=locale, name_format=name_format
        ),
        event,
    )


def get_divorce_profile(
    db_handle: DbReadBase,
    family: Family,
    args: list | None = None,
    locale: GrampsLocale = glocale,
    name_format: str | None = None,
) -> tuple[dict, Event | None]:
    """Return best available divorce information for a couple."""
    event = get_divorce_or_fallback(db_handle, family)
    if event is None:
        return {}, None
    args = args or []
    return (
        get_event_profile_for_object(
            db_handle, event, args=args, locale=locale, name_format=name_format
        ),
        event,
    )


def _format_place_type(
    place_type: PlaceType, locale: GrampsLocale = glocale
) -> dict[str, Any]:
    """Format a place type."""
    return locale.translation.sgettext(place_type.xml_str())


def get_place_profile_for_object(
    db_handle: DbReadBase,
    place: Place,
    locale: GrampsLocale = glocale,
    parent_places: bool = True,
) -> dict[str, Any]:
    """Get place profile given a Place."""
    latitude, longitude = conv_lat_lon(place.lat, place.long, format="D.D8")
    profile = {
        "gramps_id": place.gramps_id,
        "type": _format_place_type(place.get_type(), locale=locale),
        "name": place.get_name().value,
        "alternate_names": [
            place_name.value for place_name in place.get_alternative_names()
        ],
        "alternate_place_names": [
            {
                "value": place_name.value,
                "date_str": locale.date_displayer.display(place_name.date),
            }
            for place_name in place.get_alternative_names()
        ],
        "lat": float(latitude) if (latitude and longitude) else None,
        "long": float(longitude) if (latitude and longitude) else None,
    }
    if parent_places:
        parent_places_handles = []
        _place = place
        handle = None
        while True:
            for placeref in _place.get_placeref_list():
                handle = placeref.ref
                break
            if handle is None or handle in parent_places_handles:
                break
            _place = None
            try:
                _place = db_handle.get_place_from_handle(handle)
            except HandleError:
                break
            if _place is None:
                break
            parent_places_handles.append(handle)

        parent_places_value = []
        for parent_place in parent_places_handles:
            try:
                place_value = db_handle.get_place_from_handle(parent_place)
                if place_value is None:
                    continue
                parent_places_value.append(
                    get_place_profile_for_object(
                        db_handle=db_handle,
                        place=place_value,
                        locale=locale,
                        parent_places=False,
                    )
                )
            except HandleError:
                continue
        profile["parent_places"] = parent_places_value

        direct_parent_places_value = []
        for place_ref in place.get_placeref_list():
            try:
                place_value = db_handle.get_place_from_handle(place_ref.ref)
                if place_value is None:
                    continue
                direct_parent_places_value.append(
                    {
                        "place": get_place_profile_for_object(
                            db_handle=db_handle,
                            place=place_value,
                            locale=locale,
                            parent_places=False,
                        ),
                        "date_str": locale.date_displayer.display(place_ref.date),
                    }
                )
            except HandleError:
                continue
        profile["direct_parent_places"] = direct_parent_places_value
    return profile


def get_place_profile_for_handle(
    db_handle: DbReadBase,
    handle: Handle,
    locale: GrampsLocale = glocale,
    parent_places: bool = True,
) -> Union[Media, dict]:
    """Get place profile given a handle."""
    obj = get_place_by_handle(db_handle, handle)
    return get_place_profile_for_object(
        db_handle, obj, locale=locale, parent_places=parent_places
    )


def get_person_profile_for_object(
    db_handle: DbReadBase,
    person: Person,
    args: list,
    locale: GrampsLocale = glocale,
    name_format: str | None = None,
    precision: int = 3,
) -> dict[str, Any]:
    """Get person profile given a Person."""
    options = []
    if "all" in args or "ratings" in args:
        options.append("ratings")
    birth, birth_event = get_birth_profile(
        db_handle, person, args=options, locale=locale
    )
    death, death_event = get_death_profile(
        db_handle, person, args=options, locale=locale
    )
    if "all" in args or "age" in args:
        options.append("age")
        if birth_event is not None:
            birth["age"] = locale.translation.ngettext(
                "{number_of} day", "{number_of} days", 0
            ).format(number_of=0)
            if death_event is not None:
                death["age"] = (
                    Span(birth_event.date, death_event.date)
                    .format(precision=precision, dlocale=locale)
                    .strip("()")
                )
    name_displayer = NameDisplay(xlocale=locale)
    name_displayer.set_name_format(db_handle.name_formats)
    fmt_default = config.get("preferences.name-format")
    name_displayer.set_default_format(fmt_default)
    profile = {
        "handle": person.handle,
        "gramps_id": person.gramps_id,
        "sex": get_sex_profile(person),
        "birth": birth,
        "death": death,
        "name_given": name_displayer.display_given(person),
        "name_surname": person.primary_name.get_surname(),
        "name_display": (
            name_displayer.format_str(person.get_primary_name(), name_format)
            if name_format
            else name_displayer.display(person)
        ),
        "name_suffix": person.primary_name.get_suffix(),
    }
    if "all" in args or "span" in args:
        options.append("span")
    if "all" in args or "events" in args:
        options.append("events")
        if "age" not in args and "all" not in args:
            birth_event = None
        profile["events"] = [
            get_event_profile_for_handle(
                db_handle,
                event_ref.ref,
                args=options,
                base_event=birth_event,
                label="age",
                locale=locale,
                role=locale.translation.sgettext(event_ref.get_role().xml_str()),
                name_format=name_format,
                precision=precision,
            )
            for event_ref in person.event_ref_list
        ]
    if "all" in args or "families" in args:
        primary_parent_family_handle = person.get_main_parents_family_handle()
        profile["primary_parent_family"] = get_family_profile_for_handle(
            db_handle,
            primary_parent_family_handle,
            options,
            locale=locale,
            name_format=name_format,
            precision=precision,
        )
        profile["other_parent_families"] = []
        for handle in person.parent_family_list:
            if handle != primary_parent_family_handle:
                profile["other_parent_families"].append(
                    get_family_profile_for_handle(
                        db_handle,
                        handle,
                        options,
                        locale=locale,
                        name_format=name_format,
                        precision=precision,
                    )
                )
        profile["families"] = [
            get_family_profile_for_handle(
                db_handle,
                handle,
                options,
                locale=locale,
                name_format=name_format,
                precision=precision,
            )
            for handle in person.family_list
        ]
    return profile


def get_person_profile_for_handle(
    db_handle: DbReadBase,
    handle: Handle,
    args: list,
    locale: GrampsLocale = glocale,
    name_format: str | None = None,
    precision: int = 3,
) -> dict[str, Any]:
    """Get person profile given a handle."""
    try:
        obj = db_handle.get_person_from_handle(handle)
        if obj is None:
            return {}
    except HandleError:
        return {}
    return get_person_profile_for_object(
        db_handle,
        obj,
        args,
        locale=locale,
        name_format=name_format,
        precision=precision,
    )


def get_family_profile_for_object(
    db_handle: DbReadBase,
    family: Family,
    args: list[str],
    locale: GrampsLocale = glocale,
    name_format: Optional[str] = None,
    precision: int = 3,
) -> dict[str, Any]:
    """Get family profile given a Family."""
    options = []
    if "all" in args or "ratings" in args:
        options.append("ratings")
    marriage, marriage_event = get_marriage_profile(
        db_handle, family, args=options, locale=locale
    )
    divorce, divorce_event = get_divorce_profile(
        db_handle, family, args=options, locale=locale
    )
    if "all" in args or "span" in args:
        if marriage_event is not None:
            marriage["span"] = locale.translation.ngettext(
                "{number_of} day", "{number_of} days", 0
            ).format(number_of=0)
            if divorce_event is not None:
                divorce["span"] = (
                    Span(marriage_event.date, divorce_event.date)
                    .format(precision=precision, dlocale=locale)
                    .strip("()")
                )
    if "all" in args or "age" in args:
        options.append("age")
    profile = {
        "handle": family.handle,
        "gramps_id": family.gramps_id,
        "father": get_person_profile_for_handle(
            db_handle,
            family.father_handle,
            options,
            locale=locale,
            name_format=name_format,
            precision=precision,
        ),
        "mother": get_person_profile_for_handle(
            db_handle,
            family.mother_handle,
            options,
            locale=locale,
            name_format=name_format,
            precision=precision,
        ),
        "relationship": locale.translation.sgettext(family.type.xml_str()),
        "marriage": marriage,
        "divorce": divorce,
        "children": [
            get_person_profile_for_handle(
                db_handle,
                child_ref.ref,
                options,
                locale=locale,
                name_format=name_format,
                precision=precision,
            )
            for child_ref in family.child_ref_list
        ],
    }
    if profile["father"]:
        if profile["father"]["name_surname"] or profile["father"]["name_given"]:
            profile["family_surname"] = profile["father"]["name_surname"]
        elif profile["mother"]:
            profile["family_surname"] = profile["mother"]["name_surname"]
    elif profile["mother"]:
        profile["family_surname"] = profile["mother"]["name_surname"]
    else:
        profile["family_surname"] = ""
    if "all" in args or "events" in args:
        if "span" not in args and "all" not in args:
            marriage_event = None
        profile["events"] = [
            get_event_profile_for_handle(
                db_handle,
                event_ref.ref,
                args=options,
                base_event=marriage_event,
                label="span",
                locale=locale,
                name_format=name_format,
                precision=precision,
            )
            for event_ref in family.event_ref_list
        ]
    return profile


def get_family_profile_for_handle(
    db_handle: DbReadBase,
    handle: Handle,
    args: list,
    locale: GrampsLocale = glocale,
    name_format: Optional[str] = None,
    precision: int = 3,
) -> dict[str, Any]:
    """Get family profile given a handle."""
    try:
        obj = db_handle.get_family_from_handle(handle)
        if obj is None:
            return {}
    except HandleError:
        return {}
    return get_family_profile_for_object(
        db_handle,
        obj,
        args,
        locale=locale,
        name_format=name_format,
        precision=precision,
    )


def get_citation_profile_for_object(
    db_handle: DbReadBase,
    citation: Citation,
    args: list,
    locale: GrampsLocale = glocale,
) -> Citation:
    """Get citation profile given a Citation."""
    source = db_handle.get_source_from_handle(citation.source_handle)
    return {
        "source": {
            "author": source.author,
            "title": source.title,
            "pubinfo": source.pubinfo,
            "gramps_id": source.gramps_id,
        },
        "gramps_id": citation.gramps_id,
        "date": locale.date_displayer.display(citation.date),
        "page": citation.page,
    }


def get_citation_profile_for_handle(
    db_handle: DbReadBase, handle: Handle, args: list, locale: GrampsLocale = glocale
) -> Union[Family, dict]:
    """Get citation profile given a handle."""
    try:
        obj = db_handle.get_citation_from_handle(handle)
        if obj is None:
            return {}
    except HandleError:
        return {}
    return get_citation_profile_for_object(db_handle, obj, args, locale=locale)


def get_media_profile_for_object(
    db_handle: DbReadBase, media: Media, args: list, locale: GrampsLocale = glocale
) -> Media:
    """Get media profile given Media."""
    return {
        "gramps_id": media.gramps_id,
        "date": locale.date_displayer.display(media.date),
    }


def get_media_profile_for_handle(
    db_handle: DbReadBase, handle: Handle, args: list, locale: GrampsLocale = glocale
) -> Union[Media, dict]:
    """Get media profile given a handle."""
    try:
        obj = db_handle.get_media_from_handle(handle)
        if obj is None:
            return {}
    except HandleError:
        return {}
    return get_media_profile_for_object(db_handle, obj, args, locale=locale)


def catch_handle_error(method, handle):
    """Execute method on handle and return an empty dict on HandleError."""
    try:
        return method(handle)
    except HandleError:
        return {}


def get_extended_attributes(
    db_handle: DbReadBase, obj: GrampsObject, args: Optional[dict] = None
) -> dict:
    """Get extended attributes for a GrampsObject."""
    args = args or {}
    result: dict[str, list | dict[str, Any]] = {}
    do_all = False
    if "all" in args["extend"]:
        do_all = True
    if (do_all or "child_ref_list" in args["extend"]) and hasattr(
        obj, "child_ref_list"
    ):
        result["children"] = [
            catch_handle_error(db_handle.get_person_from_handle, child_ref.ref)
            for child_ref in obj.child_ref_list
        ]
    if (do_all or "citation_list" in args["extend"]) and hasattr(obj, "citation_list"):
        result["citations"] = [
            catch_handle_error(db_handle.get_citation_from_handle, handle)
            for handle in obj.citation_list
        ]
    if (do_all or "event_ref_list" in args["extend"]) and hasattr(
        obj, "event_ref_list"
    ):
        result["events"] = [
            catch_handle_error(db_handle.get_event_from_handle, event_ref.ref)
            for event_ref in obj.event_ref_list
        ]
    if (do_all or "media_list" in args["extend"]) and hasattr(obj, "media_list"):
        result["media"] = [
            catch_handle_error(db_handle.get_media_from_handle, media_ref.ref)
            for media_ref in obj.media_list
        ]
    if (do_all or "note_list" in args["extend"]) and hasattr(obj, "note_list"):
        result["notes"] = [
            catch_handle_error(db_handle.get_note_from_handle, handle)
            for handle in obj.note_list
        ]
    if (do_all or "person_ref_list" in args["extend"]) and hasattr(
        obj, "person_ref_list"
    ):
        result["people"] = [
            catch_handle_error(db_handle.get_person_from_handle, person_ref.ref)
            for person_ref in obj.person_ref_list
        ]
    if (do_all or "placeref_list" in args["extend"]) and hasattr(obj, "placeref_list"):
        result["places"] = [
            catch_handle_error(db_handle.get_place_from_handle, place_ref.ref)
            for place_ref in obj.placeref_list
        ]
    if (do_all or "reporef_list" in args["extend"]) and hasattr(obj, "reporef_list"):
        result["repositories"] = [
            catch_handle_error(db_handle.get_repository_from_handle, repo_ref.ref)
            for repo_ref in obj.reporef_list
        ]
    if (do_all or "tag_list" in args["extend"]) and hasattr(obj, "tag_list"):
        result["tags"] = [
            catch_handle_error(db_handle.get_tag_from_handle, handle)
            for handle in obj.tag_list
        ]
    if (do_all or "backlinks" in args["extend"]) and hasattr(obj, "backlinks"):
        result["backlinks"] = {}
        for class_name, backlinks in obj.backlinks.items():
            result["backlinks"][class_name] = [
                catch_handle_error(
                    db_handle.method("get_%s_from_handle", class_name.upper()), handle
                )
                for handle in backlinks
            ]
    return result


def get_backlinks(db_handle: DbReadBase, handle: Handle) -> dict[str, list[Handle]]:
    """Get backlinks to a handle.

    Will return a dictionary of the form
    `{'object_type': ['handle1', 'handle2', ...], ...}`
    """
    backlinks: dict[str, list[Handle]] = {}
    for obj_type, target_handle in db_handle.find_backlink_handles(handle):
        key = obj_type.lower()
        if key not in backlinks:
            backlinks[key] = []
        backlinks[key].append(target_handle)
    return backlinks


def _get_person_or_none(
    db_handle: DbReadBase, handle: Handle, referrer: GrampsObject
) -> Optional[Person]:
    """Get a person by handle, returning None if the reference is broken."""
    try:
        return db_handle.get_person_from_handle(handle)
    except HandleError as exc:
        _LOG.warning(
            "Broken person reference for %s %s: %s",
            referrer.__class__.__name__.lower(),
            referrer.handle,
            exc,
        )
        return None


def get_soundex(
    db_handle: DbReadBase, obj: GrampsObject, gramps_class_name: str
) -> str:
    """Return soundex code."""
    if gramps_class_name == "Family":
        person = None
        if obj.father_handle is not None:
            person = _get_person_or_none(db_handle, obj.father_handle, obj)
        if person is None and obj.mother_handle is not None:
            person = _get_person_or_none(db_handle, obj.mother_handle, obj)
        if person is None:
            return ""
    else:
        person = obj
    return soundex(person.get_primary_name().get_surname())


def get_reference_profile_for_object(
    db_handle: DbReadBase,
    obj: GrampsObject,
    locale: GrampsLocale = glocale,
    name_format: Optional[str] = None,
) -> dict:
    """Return reference profiles for an object."""
    profile = {}
    # get backlink handles
    if hasattr(obj, "backlinks"):
        backlink_handles = obj.backlinks
    else:
        # if not computed yet, do it now
        backlink_handles = get_backlinks(db_handle, obj.handle)
    if "person" in backlink_handles:
        profile["person"] = [
            get_person_profile_for_handle(
                db_handle,
                handle,
                args=[],
                locale=locale,
                name_format=name_format,
            )
            for handle in backlink_handles["person"]
        ]
    if "family" in backlink_handles:
        profile["family"] = [
            get_family_profile_for_handle(
                db_handle,
                handle,
                args=[],
                locale=locale,
                name_format=name_format,
            )
            for handle in backlink_handles["family"]
        ]
    if "event" in backlink_handles:
        profile["event"] = [
            get_event_profile_for_handle(
                db_handle,
                handle,
                args=[],
                locale=locale,
                name_format=name_format,
            )
            for handle in backlink_handles["event"]
        ]
    if "media" in backlink_handles:
        profile["media"] = [
            get_media_profile_for_handle(db_handle, handle, args=[], locale=locale)
            for handle in backlink_handles["media"]
        ]
    if "citation" in backlink_handles:
        profile["citation"] = [
            get_citation_profile_for_handle(db_handle, handle, args=[], locale=locale)
            for handle in backlink_handles["citation"]
        ]
    if "place" in backlink_handles:
        profile["place"] = [
            get_place_profile_for_handle(db_handle, handle, locale=locale)
            for handle in backlink_handles["place"]
        ]
    return profile


def get_rating(db_handle: DbReadBase, obj: GrampsObject) -> tuple[int, int]:
    """Return rating based on citations."""
    count = 0
    confidence = 0
    if hasattr(obj, "citation_list"):
        count = len(obj.citation_list)
        if hasattr(obj, "extended") and "citations" in obj.extended:
            for citation in obj.extended["citations"]:
                if citation.confidence > confidence:
                    confidence = citation.confidence
        else:
            for handle in obj.citation_list:
                try:
                    citation = db_handle.get_citation_from_handle(handle)
                except HandleError as exc:
                    _LOG.warning(
                        "Broken citation reference for %s %s: %s",
                        obj.__class__.__name__.lower(),
                        obj.handle,
                        exc,
                    )
                    continue
                if citation.confidence > confidence:
                    confidence = citation.confidence
    return count, confidence


def has_handle(
    db_handle: DbWriteBase,
    obj: GrampsObject,
) -> bool:
    """Check if an object with the same class and handle exists in the DB."""
    obj_class = obj.__class__.__name__.lower()
    method = db_handle.method("has_%s_handle", obj_class)
    return method(obj.handle)


def has_gramps_id(
    db_handle: DbWriteBase,
    obj: GrampsObject,
) -> bool:
    """Check if an object with the same class and handle exists in the DB."""
    if not hasattr(obj, "gramps_id"):  # needed for tags
        return False
    obj_class = obj.__class__.__name__.lower()
    method = db_handle.method("has_%s_gramps_id", obj_class)
    return method(obj.gramps_id)


def add_object(
    db_handle: DbWriteBase,
    obj: GrampsObject,
    trans: DbTxn,
    fail_if_exists: bool = False,
):
    """Commit a Gramps object to the database.

    If `fail_if_exists` is true, raises a ValueError if an object of
    the same type exists with the same handle or same Gramps ID.

    In the case of a family object, also updates the referenced handles
    in the corresponding person objects.
    """
    if db_handle.readonly:
        # adding objects is forbidden on a read-only db!
        abort_with_message(HTTPStatus.FORBIDDEN, "Forbidden: database is read-only")
    obj_class = obj.__class__.__name__.lower()
    if fail_if_exists:
        if has_handle(db_handle, obj):
            raise ValueError("Handle already exists.")
        if has_gramps_id(db_handle, obj):
            raise ValueError("Gramps ID already exists.")
    try:
        add_method = db_handle.method("add_%s", obj_class)
        if obj_class == "family":
            # need to add handle if not present yet!
            if not obj.handle:
                obj.handle = create_id()
            add_family_update_refs(db_handle=db_handle, obj=obj, trans=trans)
        return add_method(obj, trans)
    except AttributeError:
        raise ValueError("Database does not support writing.")


def add_family_update_refs(
    db_handle: DbWriteBase,
    obj: Family,
    trans: DbTxn,
) -> None:
    """Update the `family_list` and `parent_family_list` of family members.

    Case where the family is new.
    """
    # add family handle to parents
    for handle in [obj.get_father_handle(), obj.get_mother_handle()]:
        if handle:
            parent = db_handle.get_person_from_handle(handle)
            parent.add_family_handle(obj.handle)
            db_handle.commit_person(parent, trans)
    # for each child, add the family handle to the child
    for ref in obj.get_child_ref_list():
        child = db_handle.get_person_from_handle(ref.ref)
        child.add_parent_family_handle(obj.handle)
        db_handle.commit_person(child, trans)


# validation errors echo client input back; cap what goes into the response.
MAX_VALIDATION_ERROR_LENGTH = 200

# The Gramps schema neither requires `ref` nor forbids an empty one, so a
# reference with no target is stored as `ref = None` and breaks the XML export.
# See https://github.com/gramps-project/gramps-web-api/issues/479
REF_CLASSES = frozenset(
    {"ChildRef", "EventRef", "MediaRef", "PersonRef", "PlaceRef", "RepoRef"}
)


def _validate_refs(value: Any, path: str = "$") -> None:
    """Check recursively that every reference object has a non-empty ref.

    Raises ValueError naming the offending path, like jsonschema does.
    """
    if isinstance(value, dict):
        if value.get("_class") in REF_CLASSES and not value.get("ref"):
            raise ValueError(f"{path}: '{value['_class']}' requires a non-empty 'ref'")
        for key, item in value.items():
            _validate_refs(item, f"{path}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _validate_refs(item, f"{path}[{i}]")


def validate_object_dict(obj_dict: dict[str, Any]) -> None:
    """Validate a dict representation of a Gramps object vs. its schema.

    Raises ValueError if the object does not conform to its schema.
    """
    class_name = obj_dict.get("_class")
    obj_cls = (
        getattr(gramps.gen.lib, class_name, None)
        if isinstance(class_name, str)
        else None
    )
    # module attributes like `person` or `__path__` resolve but are not classes.
    if obj_cls is None or not hasattr(obj_cls, "get_schema"):
        # name the class: a batch POST reports no index, so it is the only
        # way to tell which of the submitted objects was rejected.
        name = repr(class_name)[:MAX_VALIDATION_ERROR_LENGTH]
        raise ValueError(f"unknown object class {name}")
    schema = obj_cls.get_schema()

    obj_dict_fixed = {k: v for k, v in obj_dict.items() if k != "complete"}

    # Gramps 5.2 added Person.OTHER = 3, but the JSON schema still caps gender
    # at 2. Patch the schema to allow the actual maximum value.
    # This patch can be removed once https://github.com/gramps-project/gramps/pull/2213
    # is merged and a new Gramps version is released.
    other = getattr(obj_cls, "OTHER", None)
    if (
        other is not None
        and obj_dict_fixed.get("gender") == other
        and schema.get("properties", {}).get("gender", {}).get("maximum") is not None
        and other > schema["properties"]["gender"]["maximum"]
    ):
        # `get_schema()` may return an object shared across calls (e.g. a
        # cached class-level schema); never mutate it in place, since that
        # would leak this one-off patch into every other caller. Copy it
        # first, since we only need a locally patched view for validation.
        schema = copy.deepcopy(schema)
        schema["properties"]["gender"]["maximum"] = other

    try:
        jsonschema.validate(obj_dict_fixed, schema)
    except jsonschema.exceptions.ValidationError as exc:
        # log the constraint but not the value: the client gets its own payload
        # echoed back, the log must not retain family tree data.
        current_app.logger.warning(
            "Schema validation failed: %s does not satisfy %s",
            exc.json_path,
            exc.validator,
        )
        message = f"{exc.json_path}: {exc.message}"
        if len(message) > MAX_VALIDATION_ERROR_LENGTH:
            message = message[:MAX_VALIDATION_ERROR_LENGTH] + "..."
        raise ValueError(message) from exc

    _validate_refs(obj_dict_fixed)


def xml_to_locale(gramps_type_name: str, string: str) -> str:
    """Translate and XML string type name to a localized type name."""
    gramps_type = getattr(gramps.gen.lib, gramps_type_name)
    typ = gramps_type()
    typ.set_from_xml_str(string)
    return str(typ)


def _set_type_from_string(type_obj, string_value: str) -> None:
    """Set a GrampsType from either an XML (English) or localized string.

    The frontend may send either English XML strings (e.g. "Birth") or
    localized strings (e.g. "Geburt" in German), depending on the
    ``valueNonLocal`` property of ``GrampsjsFormSelectType``.

    This function first tries ``set_from_xml_str()`` which handles English
    XML strings via ``_E2IMAP``. If the string is not recognized (i.e. falls
    back to Custom), it tries ``set()`` which handles localized strings via
    ``_S2IMAP``.
    """
    type_obj.set_from_xml_str(string_value)
    if type_obj.is_custom() and string_value not in type_obj._E2IMAP:
        # set_from_xml_str didn't recognize it — try localized string
        type_obj.set(string_value)


def fix_object_dict(object_dict: dict, class_name: Optional[str] = None):
    """Restore a Gramps object in simplified representation to its full form.

    This restores in particular:
    - class names
    - Gramps types are turned from strings into dictionaries
    - Gramps type names are translated to the default Gramps locale
    """
    d_out = {}
    class_name = class_name or object_dict.get("_class")
    if not class_name:
        raise ValueError("No class name specified!")
    d_out["_class"] = class_name
    for k, v in object_dict.items():
        # convert type back to dict and translate type name
        if k in ["type", "place_type", "media_type", "frel", "mrel"] or (
            k == "name" and class_name == "StyledTextTag"
        ):
            if isinstance(v, str):
                if class_name == "Family":
                    _class = "FamilyRelType"
                    obj = gramps.gen.lib.__dict__[_class]()
                    _set_type_from_string(obj, v)
                    d_out[k] = object_to_dict(obj)
                elif class_name == "RepoRef":
                    _class = "SourceMediaType"
                    obj = gramps.gen.lib.__dict__[_class]()
                    _set_type_from_string(obj, v)
                    d_out[k] = object_to_dict(obj)
                else:
                    _class = f"{class_name}Type"
                    obj = gramps.gen.lib.__dict__[_class]()
                    _set_type_from_string(obj, v)
                    d_out[k] = object_to_dict(obj)
            else:
                d_out[k] = v
        elif k == "role":
            if isinstance(v, str):
                _class = "EventRoleType"
                obj = gramps.gen.lib.__dict__[_class]()
                _set_type_from_string(obj, v)
                d_out[k] = object_to_dict(obj)
            else:
                d_out[k] = v
        elif k == "origintype":
            if isinstance(v, str):
                _class = "NameOriginType"
                obj = gramps.gen.lib.__dict__[_class]()
                _set_type_from_string(obj, v)
                d_out[k] = object_to_dict(obj)
            else:
                d_out[k] = v
        elif k in ["rect", "mother_handle", "father_handle", "famc"] and not v:
            d_out[k] = None
        elif isinstance(v, dict):
            d_out[k] = fix_object_dict(v, _get_class_name(class_name, k))
        elif isinstance(v, list):
            d_out[k] = [
                (
                    fix_object_dict(item, _get_class_name(class_name, k))
                    if isinstance(item, dict)
                    else item
                )
                for item in v
            ]
        elif k in ["complete"]:
            pass
        elif k == "date" and v is None:
            # date = None not allowed in Gramps 6.0
            d_out[k] = {"_class": "Date", "dateval": [0, 0, 0, False]}
        else:
            d_out[k] = v
    return d_out


def _get_class_name(super_name, key_name) -> str:
    """Get the correct Gramps class name for a given key in a class dict."""
    if key_name == "date":
        return "Date"
    if key_name == "media_list":
        return "MediaRef"
    if key_name == "child_ref_list":
        return "ChildRef"
    if key_name == "event_ref_list":
        return "EventRef"
    if key_name == "address_list":
        return "Address"
    if key_name == "urls":
        return "Url"
    if key_name == "lds_ord_list":
        return "LdsOrd"
    if key_name == "person_ref_list":
        return "PersonRef"
    if key_name == "surname_list":
        return "Surname"
    if key_name == "text":
        return "StyledText"
    if key_name == "place_type":
        return "PlaceType"
    if key_name == "alt_loc":
        return "Location"
    if key_name == "reporef_list":
        return "RepoRef"
    if key_name == "placeref_list":
        return "PlaceRef"
    if key_name == "tags":
        return "StyledTextTag"
    if (key_name == "name" and super_name == "Place") or key_name == "alt_names":
        return "PlaceName"
    if key_name in ["primary_name", "alternate_names"]:
        return "Name"
    if key_name == "attribute_list" and (
        super_name == "Citation" or super_name == "Source"
    ):
        return "SrcAttribute"
    elif key_name == "attribute_list":
        return "Attribute"
    raise ValueError(f"Unknown classes: {super_name}, {key_name}")


def update_object(
    db_handle: DbWriteBase,
    obj: GrampsObject,
    trans: DbTxn,
):
    """Commit a modified Gramps object to the database.

    Fails with a ValueError if the object with this handle does not
    exist, or if another object of the same type exists with the
    same Gramps ID.
    """
    if db_handle.readonly:
        # updating objects is forbidden on a read-only db!
        abort_with_message(HTTPStatus.FORBIDDEN, "Forbidden: database is read-only")
    obj_class = obj.__class__.__name__.lower()
    if not has_handle(db_handle, obj):
        raise ValueError("Cannot be used for new objects.")
    if hasattr(obj, "gramps_id") and not obj.gramps_id:
        # if the Gramps ID is empty, set it to the old one!
        handle_func = db_handle.method("get_%s_from_handle", obj_class)
        obj_old = handle_func(obj.handle)
        obj.set_gramps_id(obj_old.gramps_id)
    try:
        commit_method = db_handle.method("commit_%s", obj_class)
        if obj_class == "family":
            handle_func = db_handle.method("get_%s_from_handle", obj_class)
            obj_old = handle_func(obj.handle)
            update_family_update_refs(
                db_handle=db_handle, obj_old=obj_old, obj=obj, trans=trans
            )
        elif obj_class == "person":
            db_handle.set_birth_death_index(obj)
        elif obj_class == "event":
            # When an event type changes (e.g. Death → Birth), the birth_ref_index
            # and death_ref_index on all referring persons must be recomputed.
            # Fetch the old event to decide whether a birth/death-relevant type
            # change has occurred before paying the cost of scanning backlinks.
            old_event = db_handle.get_event_from_handle(obj.handle)
            old_type = old_event.get_type()
            new_type = obj.get_type()
            type_affects_indices = old_type != new_type and (
                old_type.is_birth()
                or old_type.is_death()
                or new_type.is_birth()
                or new_type.is_death()
            )
            # Commit the event first so that set_birth_death_index reads the new type.
            result = commit_method(obj, trans)
            if type_affects_indices:
                for _, person_handle in db_handle.find_backlink_handles(
                    obj.handle, include_classes=["Person"]
                ):
                    try:
                        person = db_handle.get_person_from_handle(person_handle)
                    except HandleError:
                        # Stale backlink or concurrently deleted person; skip.
                        continue
                    if person is None:
                        continue
                    old_birth = person.birth_ref_index
                    old_death = person.death_ref_index
                    db_handle.set_birth_death_index(person)
                    if (
                        person.birth_ref_index != old_birth
                        or person.death_ref_index != old_death
                    ):
                        db_handle.commit_person(person, trans)
            return result
        return commit_method(obj, trans)
    except AttributeError as exc:
        raise ValueError("Database does not support writing.") from exc


def update_family_update_refs(
    db_handle: DbWriteBase,
    obj_old: Family,
    obj: Family,
    trans: DbTxn,
) -> None:
    """Update the `family_list` and `parent_family_list` of family members.

    Case where the family was modified.
    """
    _fix_parent_handles(
        db_handle, obj, obj_old.get_father_handle(), obj.get_father_handle(), trans
    )
    _fix_parent_handles(
        db_handle, obj, obj_old.get_mother_handle(), obj.get_mother_handle(), trans
    )
    # fix child handles
    orig_set = set(r.ref for r in obj_old.get_child_ref_list())
    new_set = set(r.ref for r in obj.get_child_ref_list())

    # remove the family from children which have been removed
    for ref in orig_set - new_set:
        person = db_handle.get_person_from_handle(ref)
        person.remove_parent_family_handle(obj.handle)
        db_handle.commit_person(person, trans)

    # add the family to children which have been added
    for ref in new_set - orig_set:
        person = db_handle.get_person_from_handle(ref)
        person.add_parent_family_handle(obj.handle)
        db_handle.commit_person(person, trans)


def _fix_parent_handles(
    db_handle: DbWriteBase, obj: Family, orig_handle, new_handle, trans
) -> None:
    if orig_handle != new_handle:
        if orig_handle:
            person = db_handle.get_person_from_handle(orig_handle)
            person.family_list.remove(obj.handle)
            db_handle.commit_person(person, trans)
        if new_handle:
            person = db_handle.get_person_from_handle(new_handle)
            person.family_list.append(obj.handle)
            db_handle.commit_person(person, trans)


def transaction_to_json(transaction: DbTxn) -> TransactionJson:
    """Return a JSON representation of a database transaction."""
    out = []
    for recno in transaction.get_recnos(reverse=False):
        key, action, handle, old_data, new_data = transaction.get_record(recno)
        try:
            obj_cls_name = KEY_TO_CLASS_MAP[key]
        except KeyError:
            continue  # this happens for references
        trans_dict = {TXNUPD: "update", TXNDEL: "delete", TXNADD: "add"}
        item = {
            "type": trans_dict[action],
            "handle": handle,
            "_class": obj_cls_name,
            "old": None if old_data is None else remove_object(old_data),
            "new": None if new_data is None else remove_object(new_data),
        }
        out.append(item)
    return out


def reverse_transaction(transaction_list: TransactionJson) -> TransactionJson:
    """Reverse a JSON representation of a database transaction."""
    transaction_reversed = []
    type_reversed = {"add": "delete", "delete": "add", "update": "update"}
    for item in reversed(transaction_list):
        item_reversed = {
            "type": type_reversed[item["type"]],
            "handle": item["handle"],
            "_class": item["_class"],
            "old": item["new"],
            "new": item["old"],
        }
        transaction_reversed.append(item_reversed)
    return transaction_reversed


def hash_object(obj: GrampsObject) -> str:
    """Generate a SHA256 hash for a Gramps object's data."""
    data = object_to_string(obj).encode()
    return sha256(data).hexdigest()


def filter_missing_files(objects: list[Media]) -> list[Media]:
    """Filter media objects returning only ones where the file is missing."""
    tree = get_tree_from_jwt()
    db_handle = get_db_handle()
    handler = get_media_handler(db_handle, tree=tree)
    objects_existing = handler.filter_existing_files(objects, db_handle=db_handle)
    handles_existing = set(obj.handle for obj in objects_existing)
    return [obj for obj in objects if obj.handle not in handles_existing]


def get_missing_media_file_handles(
    db_handle: DbReadBase, handles: list[str]
) -> list[str]:
    """Filter media handles returning only ones where the file is missing."""
    objects = [db_handle.get_media_from_handle(handle) for handle in handles]
    objects_missing = filter_missing_files(objects)
    return [obj.handle for obj in objects_missing]


def get_one_relationship(
    db_handle: DbReadBase,
    person1: Person,
    person2: Person,
    depth: int,
    locale: GrampsLocale = glocale,
) -> tuple[str, int, int]:
    """Get a relationship string and the number of generations between the people."""
    calc = get_relationship_calculator(reinit=True, clocale=locale)
    # the relationship calculation can be slow when depth is set to a large value
    # even when the relationship path is short. To avoid this, we are iterating
    # trying once with depth = 5
    if depth > 5:
        calc.set_depth(5)
        rel_string, dist_orig, dist_other = calc.get_one_relationship(
            db_handle, person1, person2, extra_info=True, olocale=locale
        )
        if dist_orig > -1:
            return rel_string, dist_orig, dist_other
    calc.set_depth(depth)
    return calc.get_one_relationship(
        db_handle, person1, person2, extra_info=True, olocale=locale
    )


def get_importers(extension: str | None = None):
    """Extract and return list of importers."""
    importers = []
    plugin_manager = BasePluginManager.get_instance()
    for plugin in plugin_manager.get_import_plugins():
        if extension is not None and extension != plugin.get_extension():
            continue
        if plugin.get_extension() in DISABLED_IMPORTERS:
            continue
        importer = {
            "name": plugin.get_name(),
            "description": plugin.get_description(),
            "extension": plugin.get_extension(),
            "module": plugin.get_module_name(),
        }
        importers.append(importer)
    return importers


def detect_gedcom_major_version(path: str) -> int:
    """Detect the GEDCOM version from a GEDCOM file.

    Args:
        path: Path to the GEDCOM file.

    Returns:
        The major version number (e.g., 5 or 7). Returns 0 if not found.

    This function parses the GEDCOM file header looking for the VERS tag
    within the HEAD section. It uses latin-1 encoding which is compatible
    with both GEDCOM 5.x (ANSEL) and GEDCOM 7.x (UTF-8) files.
    """
    with open(path, encoding="latin-1") as f:
        in_head = False
        for line in f:
            parts = line.strip().split(maxsplit=2)
            if len(parts) < 2:
                continue

            level, tag = parts[0], parts[1]

            if level == "0":
                if tag == "HEAD":
                    in_head = True
                elif in_head:
                    break

            elif in_head and tag == "VERS" and len(parts) == 3:
                version = parts[2]
                match = re.search(r"\d+", version)
                gedcom_major_version = int(match.group()) if match else 0
                return gedcom_major_version

    return 0


def remove_mediapath_from_gramps_xml(file_name: FilenameOrPath) -> None:
    """Remove the <mediapath> tag from a Gramps XML file.

    This function handles both compressed (.gramps with gzip) and uncompressed
    Gramps XML files. The <mediapath> tag can cause import failures and needs
    to be removed before import.

    Args:
        file_name: Path to the Gramps XML file.
    """
    # Try to read as gzipped file first
    try:
        with gzip.open(file_name, "rb") as f:
            content = f.read()
        is_compressed = True
    except (OSError, gzip.BadGzipFile):
        # Not gzipped or can't read as gzip: fall back to plain file
        with open(file_name, "rb") as f:
            content = f.read()
        is_compressed = False

    # Remove the mediapath tag using regex
    # Match <mediapath>...</mediapath> or <mediapath/> (empty tag)
    # The pattern handles both multiline and single-line cases
    pattern = rb"<mediapath\s*>.*?</mediapath\s*>|<mediapath\s*/>"
    content_modified = re.sub(pattern, b"", content, flags=re.DOTALL)

    # Write back to the file
    if is_compressed:
        with gzip.open(file_name, "wb") as f:
            f.write(content_modified)
    else:
        with open(file_name, "wb") as f:
            f.write(content_modified)


def _ensure_plugins_registered() -> None:
    """Make sure gramps' import/export plugins (and everything else in
    PLUGINS_DIR/USER_PLUGINS) are registered in this process.

    gramps.gen.db.utils.make_database() does this itself as a side effect
    of looking up the requested backend id (see its own `if not pdata:`
    fallback) -- which is *why* nothing in gramps-web-api has ever needed
    to call this explicitly before: some make_database(...) call (e.g.
    ImporterFileResource.post()'s get_db_handle(), which resolves the
    real tree's backend) has always run first and registered everything
    as a byproduct. make_scratch_db() constructing FastSQLite() directly
    (see below) skips that lookup, and dry_run_import()'s Celery task
    calls it *before* any such get_db_handle() -- so in a fresh worker
    process, nothing else triggers registration in time, and
    get_import_plugins() silently returns an empty list (an import
    "succeeds" having matched zero objects, since nothing raises). Same
    guarded check make_database() uses, so this is a no-op once plugins
    are already registered.
    """
    pmgr = BasePluginManager.get_instance()
    if not pmgr.get_plugin("sqlite"):
        pmgr.reg_plugins(PLUGINS_DIR, None, None)
        pmgr.reg_plugins(USER_PLUGINS, None, None, load_on_reg=True)


def make_scratch_db() -> DbWriteBase:
    """Create the throwaway in-memory Gramps DB used both to preview an
    import (dry_run_import) and, when the real tree is empty, to actually
    run it (see run_import's empty-tree fast path / bulk_copy).

    Uses FastSQLite directly (bypassing make_database()'s plugin lookup
    for the "sqlite" id -- make_database() just does `database_class()`
    with no arguments, so this is equally valid) so
    drop_bulk_import_indexes() is available regardless of whether the
    installed gramps-core ships it -- see fast_sqlite.py. That lookup's
    plugin-registration side effect is replicated explicitly instead, via
    _ensure_plugins_registered() -- see its docstring for why skipping it
    silently breaks imports in a fresh process.
    """
    _ensure_plugins_registered()
    db_handle = FastSQLite()
    db_handle.load(":memory:")
    db_handle.set_feature("skip-import-additions", True)
    db_handle.set_prefixes(
        config.get("preferences.iprefix"),
        config.get("preferences.oprefix"),
        config.get("preferences.fprefix"),
        config.get("preferences.sprefix"),
        config.get("preferences.cprefix"),
        config.get("preferences.pprefix"),
        config.get("preferences.eprefix"),
        config.get("preferences.rprefix"),
        config.get("preferences.nprefix"),
    )
    return db_handle


# Every table make_scratch_db()'s plain sqlite backend creates (see
# gramps/plugins/db/dbapi/dbapi.py's _create_schema) with a bare
# (handle, json_data) shape -- excludes derived/secondary columns
# (given_name, surname, title, ...), which bulk_copy() deliberately leaves
# for rebuild_secondary() to fill in afterward rather than reproducing here.
_BULK_COPY_TABLES = (
    "person",
    "family",
    "event",
    "place",
    "media",
    "source",
    "citation",
    "repository",
    "note",
    "tag",
)


def _insert_rows(dbapi, table: str, columns: list[str], rows: list[tuple]) -> None:
    """Insert `rows` (each matching `columns`) into `table`.

    Uses the backend's own bulk_insert() -- every real backend
    (sqlite/postgresql/sharedpostgresql) has one: the Postgres ones page
    through psycopg2's execute_values() (one multi-row INSERT per page
    instead of one round trip per row), sqlite's uses executemany() (no
    round trip to save, but skips the per-row Python/interpreter
    overhead of looping individual execute() calls). Falls back to a
    plain execute() per row only for a hypothetical backend with
    neither.
    """
    if not rows:
        return
    # TEMP DEBUG -- remove before this goes anywhere real.
    force_row_by_row = os.environ.get("GRAMPS_WEBAPI_FORCE_ROW_BY_ROW_INSERT")
    bulk_insert = None if force_row_by_row else getattr(dbapi, "bulk_insert", None)
    if bulk_insert is not None:
        bulk_insert(table, columns, rows)
        return
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    for row in rows:
        dbapi.execute(sql, list(row))


def _supports_inline_secondary_columns(real_db: DbWriteBase) -> bool:
    """Whether real_db's backend can compute secondary (derived) columns
    from an object alone, with no DB access -- see
    DbWriteBase.get_secondary_columns(). If not, callers must fall back
    to real_db.rebuild_secondary() to backfill those columns instead.

    Deliberately does not assume DbWriteBase.get_secondary_columns
    exists: that hook is an uncommitted gramps-core change with no
    release timeline we control, so a plain, currently-released
    gramps-core has no such attribute on DbWriteBase at all. A backend
    that defines get_secondary_columns() directly on itself (e.g. the
    SharedPostgreSQL/PostgreSQL addons, which don't wait on gramps-core
    for this) must still be detected correctly either way.
    """
    method = getattr(type(real_db), "get_secondary_columns", None)
    if method is None:
        return False
    base_method = getattr(DbWriteBase, "get_secondary_columns", None)
    return base_method is None or method is not base_method


def _prefixed(rows: list[tuple], treeid: Optional[int]) -> list[tuple]:
    """Prepend `treeid` to each row, or pass `rows` through unchanged for
    a single-tenant backend (treeid is None)."""
    if treeid is None:
        return rows
    return [(treeid, *row) for row in rows]


def _bulk_copy_table(
    scratch: DbWriteBase,
    real_db: DbWriteBase,
    table: str,
    treeid: Optional[int],
    inline_secondary: bool,
) -> list[tuple]:
    """Stream `table` out of scratch in cursor-sized chunks (its
    arraysize, ARRAYSIZE == 1000 -- see Cursor.__enter__) and bulk-insert
    each chunk into real_db, instead of loading the whole table into
    memory at once with fetchall(). A table can be the largest thing in
    a tree (events/citations easily run into the hundreds of thousands
    for a large genealogy), so this bounds bulk_copy()'s memory use to
    one chunk rather than one full table.

    When `inline_secondary` is true, folds each row's derived columns
    (given_name, surname, title, ...) into the same INSERT by computing
    them from its json_data -- avoiding the separate SELECT+UPDATE per
    row that rebuild_secondary() would otherwise need to backfill them
    afterward. Uses real_db.get_secondary_columns(), so column naming
    (e.g. SharedPostgreSQL's reserved-word renaming, desc -> desc_) is
    handled the same way it already is for a normal single-object commit.

    Returns the raw (handle, json_data) rows for the "person" table only
    (needed afterward for gender-stats rebuild, which needs every person
    in hand); an empty list for every other table.
    """
    person_rows: list[tuple] = []
    extra_columns: Optional[list[str]] = None
    with scratch.dbapi.cursor() as cur:
        cur.execute(f"SELECT handle, json_data FROM {table}")
        while True:
            raw_rows = cur.fetchmany()
            if not raw_rows:
                break
            if table == "person":
                person_rows.extend(raw_rows)

            if not inline_secondary:
                columns = (["treeid"] if treeid is not None else []) + [
                    "handle",
                    "json_data",
                ]
                rows = _prefixed(raw_rows, treeid)
            else:
                out_rows = []
                for handle, json_data in raw_rows:
                    obj = string_to_object(json_data)
                    secondary = real_db.get_secondary_columns(obj)
                    if extra_columns is None:
                        extra_columns = list(secondary.keys())
                    prefix = (treeid,) if treeid is not None else ()
                    # Matches what _update_secondary_values() already does
                    # for a normal single-row UPDATE (e.g. Person.private
                    # is a Python bool, but its physical column is
                    # INTEGER -- psycopg2 sends a bare bool as SQL
                    # boolean, which Postgres then refuses to write into
                    # an integer column).
                    extra_values = real_db._sql_cast_list(
                        [secondary[col] for col in extra_columns]
                    )
                    out_rows.append(prefix + (handle, json_data) + tuple(extra_values))
                columns = (
                    (["treeid"] if treeid is not None else [])
                    + ["handle", "json_data"]
                    + (extra_columns or [])
                )
                rows = out_rows

            _insert_rows(real_db.dbapi, table, columns, rows)
    return person_rows


def _rebuild_gender_stats(real_db: DbWriteBase, person_rows: list[tuple]) -> None:
    """Rebuild real_db's GenderStats from the person rows just bulk-copied
    in.

    bulk_copy() never copies the gender_stats table itself, and
    rebuild_secondary()'s own tail (get_gender_stats()) just reads back
    whatever's already in that table rather than recomputing it -- so
    without this, a fast-path import leaves gender stats empty.
    """
    gstats = GenderStats()
    for _handle, json_data in person_rows:
        gstats.count_person(string_to_object(json_data))
    real_db.genderStats = gstats
    real_db.save_gender_stats(gstats)


def bulk_copy(scratch: DbWriteBase, real_db: DbWriteBase) -> None:
    """Copy every row from an empty scratch DB straight into real_db.

    Only valid when real_db is empty: there is no gramps_id/handle
    reconciliation here, just a raw copy of (handle, json_data) per table
    plus the reference table -- see run_import's `db_handle.get_total() ==
    0` fast path, which is the only caller.

    Derived/secondary columns (given_name, surname, title, ...) are
    computed from each row's json_data and included directly in that
    row's INSERT when real_db's backend supports it (see
    _bulk_copy_table()); otherwise they're left unset here and backfilled
    by a rebuild_secondary() call at the end, the same way this worked
    before per-backend inline support existed. Every table is streamed
    out of scratch in chunks rather than loaded in full with fetchall(),
    to bound memory use on a large tree.
    """
    # SharedPostgreSQL's tables are multi-tenant (one shared table per
    # object type across every tree, discriminated by a treeid column);
    # plain sqlite/postgresql backends are one-tree-per-database and have
    # no such column. dbapi.treeid only exists on the former.
    treeid = getattr(real_db.dbapi, "treeid", None)
    inline_secondary = _supports_inline_secondary_columns(real_db)

    person_rows: list[tuple] = []
    for table in _BULK_COPY_TABLES:
        rows = _bulk_copy_table(scratch, real_db, table, treeid, inline_secondary)
        if rows:
            person_rows = rows

    with scratch.dbapi.cursor() as cur:
        cur.execute(
            "SELECT obj_handle, obj_class, ref_handle, ref_class FROM reference"
        )
        while True:
            ref_rows = cur.fetchmany()
            if not ref_rows:
                break
            _insert_rows(
                real_db.dbapi,
                "reference",
                (["treeid"] if treeid is not None else [])
                + ["obj_handle", "obj_class", "ref_handle", "ref_class"],
                _prefixed(ref_rows, treeid),
            )

    real_db.dbapi.commit()
    # A bulk INSERT finishes far faster than autovacuum's normal cycle, so
    # the tables just written still carry stale (pre-import) planner
    # statistics -- without this, any lookups against them (including
    # rebuild_secondary()'s, on the fallback path below) can get planned
    # as sequential scans instead of index scans. Cheap enough on an
    # otherwise-empty tree's worth of tables to run unconditionally
    # rather than special-case any one backend.
    for table in (*_BULK_COPY_TABLES, "reference"):
        real_db.dbapi.execute(f"ANALYZE {table};")

    if not inline_secondary:
        # Fallback: backend can't compute secondary columns from an
        # object alone, so backfill them the old way (SELECT+UPDATE per
        # row).
        real_db.rebuild_secondary(callback=None)
    _rebuild_gender_stats(real_db, person_rows)
    real_db.request_rebuild()


def _flush_and_snapshot_metadata(db: DbWriteBase) -> dict:
    """Flush every in-memory-only metadata attribute to `db`'s metadata
    table, then read the table back into a dict keyed by setting name.

    Setters called during import land in two different places depending
    on which one a given importer/format uses: some (e.g.
    set_default_person_handle()) write straight to the metadata table via
    _set_metadata(); others (set_researcher(), bookmarks, custom
    type/attribute registries -- see DbGeneric._set_all_metadata()) only
    mutate an in-memory attribute on the DB object, normally flushed to
    the table by close(). For an in-memory (":memory:") scratch DB, close()
    skips that flush entirely (DbGeneric.close()'s own `if self._directory
    != ":memory:":` guard) -- so without calling _set_all_metadata()
    directly here (which has no such guard itself), values like the
    researcher name would never reach the metadata table at all, no
    matter when this snapshot is taken.
    """
    db._set_all_metadata()
    return {key: db._get_metadata(key) for key in db._get_metadata_keys()}


def _propagate_metadata(
    scratch: DbWriteBase, real_db: DbWriteBase, baseline: dict
) -> None:
    """Copy whatever metadata import_function() added or changed on
    scratch beyond `baseline` into real_db.

    Format importers commonly set tree-level metadata while parsing --
    e.g. importxml.py calls set_researcher()/set_default_person_handle()
    for a file's <researcher>/home-person data. On the empty-tree fast
    path that lands on the *scratch* DB (since import_function() is
    called with scratch, not real_db), and bulk_copy() deliberately never
    touches the metadata table (it also holds real_db's own pre-existing
    tree-level settings, which must not be blindly overwritten) -- so
    without this, that data would be silently lost. Diffing against a
    pre-parse baseline (rather than copying everything) is what keeps
    make_scratch_db()'s own setup calls (set_prefixes(), using
    server-global config) from being copied over real_db's own prefixes.
    `baseline` must come from _flush_and_snapshot_metadata(scratch),
    called before import_function() runs, and this function expects
    _flush_and_snapshot_metadata(scratch) to have been called *again*
    (its return value discarded) right after import_function() returns,
    so scratch's own metadata table reflects the parsed state, not just
    whatever a handful of setters wrote immediately.
    """
    for key in scratch._get_metadata_keys():
        value = scratch._get_metadata(key)
        try:
            unchanged = key in baseline and baseline[key] == value
        except Exception:
            # Some metadata value types may not support == cleanly --
            # default to propagating rather than silently dropping data,
            # since that's the exact failure mode this function exists to
            # avoid.
            unchanged = False
        if not unchanged:
            real_db._set_metadata(key, value)

    # "researcher" is one of the keys DbGeneric._set_all_metadata() writes
    # from an in-memory attribute (self.owner) rather than something a
    # setter persists immediately (see that method, and set_researcher()'s
    # own `self.owner.set_from(owner)`). real_db.close() calls
    # _set_all_metadata() again at the end of the request -- since it's
    # not a ":memory:" DB, the guard that skips that call for scratch
    # doesn't apply to it -- and that later call writes whatever
    # real_db.owner currently holds, silently overwriting the direct
    # _set_metadata() write above unless real_db's own attribute is
    # updated to match. (bookmarks and the custom type/attribute registries
    # are flushed the same deferred way and have the same gap; only
    # researcher is fixed here, matching what was actually reported lost.)
    real_db.owner.set_from(scratch.get_researcher())


def _tree_lock_key(db_handle: DbWriteBase) -> Optional[int]:
    """Postgres advisory-lock key for db_handle's tree, if the backend
    supports one. Only SharedPostgreSQL needs this: it's multi-tenant
    (every tree shares the same tables, discriminated by a `treeid`
    column), so two concurrent empty-tree imports for the *same* tree
    could otherwise both pass the `get_total() == 0` check and both
    bulk-copy in at once. Plain sqlite/postgresql are one-tree-per-
    database, so there's no shared table for two *different* trees to
    corrupt this way."""
    return getattr(db_handle.dbapi, "treeid", None)


def run_fast_path_copy(
    scratch: DbWriteBase, real_db: DbWriteBase, baseline_metadata: dict
) -> None:
    """Bulk-copy scratch into real_db under an advisory lock (when the
    backend has one), re-checking the empty-tree precondition once the
    lock is held, and rolling back to empty on any failure.

    run_import()'s initial `db_handle.get_total() == 0` check happens
    before this, unlocked -- and that window includes the entire file
    parse, not just the copy, so a concurrent writer has plenty of time to
    act in it. Re-checking here, lock held, closes that race: if the tree
    is no longer empty, this aborts loudly instead of bulk-copying without
    the gramps_id/handle reconciliation that normally protects a
    non-empty tree.
    """
    lock_key = _tree_lock_key(real_db)
    if lock_key is not None:
        real_db.dbapi.execute("SELECT pg_advisory_lock(?)", [lock_key])
    try:
        if real_db.get_total() != 0:
            raise RuntimeError(
                "Tree is no longer empty (a concurrent write happened during "
                "import) -- please retry the import."
            )
        try:
            bulk_copy(scratch, real_db)
            _propagate_metadata(scratch, real_db, baseline_metadata)
        except Exception:
            # real_db was just confirmed empty above, so "delete
            # everything" undoes exactly this attempt and nothing else --
            # leaves the tree as it started rather than a partially
            # copied, partially reindexed mess.
            from .delete import delete_all_objects

            delete_all_objects(real_db)
            raise
    finally:
        if lock_key is not None:
            real_db.dbapi.execute("SELECT pg_advisory_unlock(?)", [lock_key])


def scratch_object_counts(db_handle: DbWriteBase) -> dict[str, int]:
    """Object counts for a (scratch or real) db_handle, in the shape the
    importer preview / quota check expect."""
    return {
        "people": db_handle.get_number_of_people(),
        "families": db_handle.get_number_of_families(),
        "sources": db_handle.get_number_of_sources(),
        "citations": db_handle.get_number_of_citations(),
        "events": db_handle.get_number_of_events(),
        "media": db_handle.get_number_of_media(),
        "places": db_handle.get_number_of_places(),
        "repositories": db_handle.get_number_of_repositories(),
        "notes": db_handle.get_number_of_notes(),
        "tags": db_handle.get_number_of_tags(),
    }


def parse_import_to_scratch(
    file_name: FilenameOrPath,
    extension: str,
    task: Optional[Task] = None,
    delete: bool = True,
) -> tuple[DbWriteBase, dict]:
    """Parse `file_name` into a fresh scratch DB and return it, still
    open, along with its pre-parse metadata baseline (see
    _flush_and_snapshot_metadata).

    This is the plugin-dispatch import path (everything run_import()
    does other than its GEDCOM7 special case, which writes straight to
    whatever db_handle it's given and never goes through a scratch DB at
    all -- see run_import()).

    The caller owns the returned DB's lifecycle from here (close it when
    done) and decides what to do with it:
    - dry_run_import() just reads object counts off it and closes it.
    - a real import into an empty tree can bulk-copy it into the real
      tree afterward (see tasks.py's import_file()) -- reusing this one
      parse instead of run_import() parsing the same file a second time
      from scratch, which is what used to happen unconditionally (every
      real import first called dry_run_import() for a people-count to
      quota-check against, threw that parse away, then run_import()
      parsed the same file again for real).

    Raises (via abort_with_message) on failure, same as run_import().
    """
    if extension.lower() == "gramps":
        # Remove mediapath tag from Gramps XML files before import
        # This is necessary because the mediapath tag can cause import failures
        try:
            remove_mediapath_from_gramps_xml(file_name)
        except Exception as e:
            # Log the error but continue with import attempt
            current_app.logger.warning(
                f"Failed to remove mediapath tag from {file_name}: {e}"
            )

    plugin_manager = BasePluginManager.get_instance()
    import_function = None
    for plugin in plugin_manager.get_import_plugins():
        if extension == plugin.get_extension():
            import_function = plugin.get_import_function()
            break
    if import_function is None:
        abort_with_message(422, f"No importer found for extension {extension}")

    user = UserTaskProgress(task=task) if task else User()

    scratch = make_scratch_db()
    try:
        baseline_metadata = _flush_and_snapshot_metadata(scratch)
        # Drop scratch's own non-essential secondary indexes (surname,
        # given_name, title, page, desc, enclosed_by,
        # reference_ref_handle -- see DBAPI._BULK_IMPORT_DROPPABLE_INDEXES)
        # before parsing into it: maintaining them incrementally on every
        # single insert is wasted work here, since nothing else in this
        # fast path ever looks them up -- bulk_copy() reads scratch back
        # out with a plain sequential SELECT per table, not an indexed
        # lookup. We deliberately never call the paired
        # rebuild_bulk_import_indexes() -- see this function's own
        # docstring for what happens to `scratch` afterward; none of
        # those callers need scratch's indexes rebuilt either.
        # getattr-guarded: no-op on a gramps version without this hook.
        drop_scratch_indexes = getattr(scratch, "drop_bulk_import_indexes", None)
        if drop_scratch_indexes is not None:
            drop_scratch_indexes()
        result = import_function(scratch, str(file_name), user)
        if not result:
            abort_with_message(500, "Import failed")
        # Flush whatever set_researcher()/bookmarks/custom-type
        # registries the parse just populated in memory into scratch's
        # own metadata table (see _flush_and_snapshot_metadata's
        # docstring) -- return value unused, just the side effect.
        _flush_and_snapshot_metadata(scratch)
    except Exception:
        scratch.close()
        raise
    finally:
        if delete:
            try:
                os.remove(file_name)
            except OSError as e:
                current_app.logger.warning(
                    f"Failed to delete temporary file {file_name}: {e}"
                )
    return scratch, baseline_metadata


def run_import(
    db_handle: DbWriteBase,
    file_name: FilenameOrPath,
    extension: str,
    delete: bool = True,
    task: Optional[Task] = None,
    use_fast_path: bool = True,
) -> None:
    """Import a file."""
    if extension.lower() == "ged" and detect_gedcom_major_version(str(file_name)) == 7:
        try:
            gramps_gedcom7.import_gedcom(input_file=file_name, db=db_handle)
        except ValueError as e:
            # ValueError indicates invalid file format or encoding (e.g., not UTF-8)
            abort_with_message(422, f"Invalid GEDCOM file: {e}")
        except Exception as e:
            # Unexpected errors - log for debugging
            current_app.logger.exception("GEDCOM7 import failed with unexpected error")
            abort_with_message(500, f"Import failed: {e}")
        finally:
            if delete:
                try:
                    os.remove(file_name)
                except OSError as e:
                    # Log but don't let cleanup failures mask the import error
                    current_app.logger.warning(
                        f"Failed to delete temporary file {file_name}: {e}"
                    )
        return
    if (
        use_fast_path
        and not os.environ.get("GRAMPS_WEBAPI_FORCE_OLD_IMPORT_PATH")
        and db_handle.get_total() == 0
    ):
        # Empty-tree fast path: parse into a scratch in-memory DB (no
        # legalize_id() collision checks needed -- there's nothing to
        # collide with) and bulk-copy the result in, instead of parsing
        # the file a second time straight into the real (likely
        # networked Postgres) tree.
        scratch, baseline_metadata = parse_import_to_scratch(
            file_name, extension, task=task, delete=delete
        )
        try:
            run_fast_path_copy(scratch, db_handle, baseline_metadata)
        finally:
            scratch.close()
        return

    if extension.lower() == "gramps":
        try:
            remove_mediapath_from_gramps_xml(file_name)
        except Exception as e:
            current_app.logger.warning(
                f"Failed to remove mediapath tag from {file_name}: {e}"
            )
    plugin_manager = BasePluginManager.get_instance()
    for plugin in plugin_manager.get_import_plugins():
        if extension == plugin.get_extension():
            import_function = plugin.get_import_function()
            user = UserTaskProgress(task=task) if task else User()
            result = import_function(db_handle, str(file_name), user)
            if delete:
                os.remove(file_name)
            if not result:
                abort_with_message(500, "Import failed")
            return


def dry_run_import(
    file_name: FilenameOrPath,
    extension: str,
) -> Optional[dict[str, int]]:
    """Import a file into an in-memory database and returns object counts."""
    scratch, _baseline_metadata = parse_import_to_scratch(
        file_name, extension, delete=False
    )
    result = scratch_object_counts(scratch)
    scratch.close()
    return result


def app_has_semantic_search() -> bool:
    """Indicate whether the app supports semantic search."""
    return bool(current_app.config.get("VECTOR_EMBEDDING_MODEL"))


def normalize_etag(etag: str | None) -> str | None:
    """Normalize an Etag"""
    if not etag:
        return None
    # Remove weak validator (W/) and suffix like :zstd or -gzip
    if "/" in etag:
        etag = etag.split("/", 1)[1]
    if ":" in etag:
        etag = etag.split(":", 1)[0]
    elif "-" in etag:
        etag = etag.split("-", 1)[0]
    etag = etag.strip('"')
    return etag


def etag_unchanged(etag: str) -> bool:
    """Check whether the if none match header agrees with the current etag.

    The header may carry a comma-separated list of validators. The wildcard
    `*` is not treated as a match.
    """
    header = request.headers.get("If-None-Match")
    if not header:
        return False
    return any(
        normalize_etag(candidate.strip()) == etag for candidate in header.split(",")
    )


def return_304_if_unchanged(response: Response, etag: str) -> Response:
    """Change the response status to 304 if the if none match header agrees
    with the current etag."""
    if etag_unchanged(etag):
        response.status = "304"
        response.response = ""
    return response
