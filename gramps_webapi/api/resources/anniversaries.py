#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      Gramps Web contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#

"""Anniversaries ICS resource."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, cast

from flask import Response, request
from gramps.gen import filters as gramps_filters
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db.base import DbReadBase
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.errors import HandleError
from gramps.gen.lib import Date, Event, EventType, Family, Person
from gramps.gen.lib.date import gregorian
from gramps.gen.proxy.cache import CacheProxyDb
from gramps.gen.utils.alive import probably_alive
from gramps.gen.utils.grampslocale import GrampsLocale
from marshmallow import Schema, ValidationError
from webargs import fields, validate

from ...auth import (
    get_permissions,
    is_tree_disabled,
)
from ...auth.const import ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS, PERM_VIEW_PRIVATE
from ...const import GRAMPS_NAMESPACES
from ...types import Handle
from ..blueprint import api_blueprint
from ..cache import get_db_last_change_timestamp, request_cache
from ..ratelimiter import limiter
from ..util import (
    abort_with_message,
    close_db,
    get_db_manager,
    get_db_outside_request,
    get_locale_for_language,
    get_tree_id,
)
from . import Resource
from .access_tokens import get_active_user_from_access_token
from .filters import apply_filter, get_custom_filters
from .util import get_family_name_localized

ICS_FORMAT_VERSION = 2
ICS_CACHE_TIMEOUT = 86400


@dataclass
class AnniversaryEvent:
    """An event and the visible participants found while collecting it."""

    event: Event
    date_components: tuple[int, int, int]
    participants: dict[tuple[str, str], str] = field(default_factory=dict)


def _token_limit_key() -> str:
    """Keep token values out of rate-limiter storage."""
    return hashlib.sha256(request.args.get("token", "").encode()).hexdigest()


def _calendar_etag(
    tree_id: str,
    tree_name: str,
    view_private: bool,
    args: dict,
    timestamp,
    locale: GrampsLocale,
    filter_definitions: list[dict],
) -> str:
    """Identify the feed without opening the tree database."""
    normalized = {key: value for key, value in args.items() if key != "token"}
    normalized["event_types"] = sorted(
        {
            value.strip().casefold()
            for value in args.get("event_types", [])
            if value.strip()
        }
    )
    dimensions = (
        ICS_FORMAT_VERSION,
        tree_id,
        tree_name,
        timestamp,
        view_private,
        str(locale.language),
        normalized,
        filter_definitions,
        (
            datetime.now(timezone.utc).date().isoformat()
            if args["living_only"]
            else None
        ),
    )
    return hashlib.sha256(json.dumps(dimensions, sort_keys=True).encode()).hexdigest()


def _calendar_response(payload: str, etag: str) -> Response:
    """Return a calendar or its conditional response with refresh headers."""
    unchanged = request.if_none_match.contains_weak(etag)
    response = Response(
        "" if unchanged else payload,
        status=304 if unchanged else 200,
        mimetype="text/calendar",
    )
    response.headers["Content-Disposition"] = "inline; filename=anniversaries.ics"
    response.cache_control.private = True
    response.cache_control.max_age = ICS_CACHE_TIMEOUT
    response.expires = datetime.now(timezone.utc) + timedelta(seconds=ICS_CACHE_TIMEOUT)
    response.set_etag(etag, weak=True)
    return response


def _escape_ics_text(value: str) -> str:
    """Escape RFC 5545 text, including standalone carriage returns."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
    )


def _fold_ics_line(line: str) -> str:
    """Fold at 75 UTF-8 octets without splitting a code point."""
    parts = []
    current = ""
    size = 0
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > 75:
            parts.append(current)
            current, size = " ", 1
        current += char
        size += width
    parts.append(current)
    return "\r\n".join(parts)


def _get_anniversary_date_components(event: Event) -> tuple[int, int, int] | None:
    """Return fully specified exact Gregorian dates only."""
    if event.date is None or not event.date.is_regular():
        return None
    event_date = gregorian(event.date)
    year, month, day = (
        event_date.get_year(),
        event_date.get_month(),
        event_date.get_day(),
    )
    try:
        datetime(year, month, day)
    except ValueError:
        return None
    return year, month, day


def _get_record(getter: Callable, handle: str):
    """Ignore dangling references and records hidden by the privacy proxy."""
    try:
        return getter(handle)
    except HandleError:
        return None


def _resolve_anchor_people_handles(
    db_handle, anchor_gramps_id: str, generation_depth: int
) -> set[Handle]:
    """Resolve the legacy direct-line scope through Gramps filter rules."""
    anchor = db_handle.get_person_from_gramps_id(anchor_gramps_id)
    if anchor is None:
        return set()
    rules = {
        "function": "or",
        "rules": [
            {
                "name": "IsLessThanNthGenerationAncestorOf",
                "values": [anchor_gramps_id, generation_depth],
            },
            {
                "name": "IsLessThanNthGenerationDescendantOf",
                "values": [anchor_gramps_id, generation_depth],
            },
        ],
    }
    handles = cast(list[Handle], list(db_handle.get_person_handles(sort_handles=False)))
    return set(
        apply_filter(
            db_handle,
            {"rules": json.dumps(rules)},
            "Person",
            handles,
        )
    )


def _filter_dependencies(args: dict) -> tuple[list[dict[str, Any]], bool]:
    """Return native saved-filter definitions that influence this feed."""
    if not any(key.endswith(("filter", "rules")) for key in args):
        return [], False
    gramps_filters.reload_custom_filters()
    definitions: list[dict[str, Any]] = [
        {
            "namespace": namespace,
            "filters": get_custom_filters({}, namespace, reload=False),
        }
        for namespace in sorted(set(GRAMPS_NAMESPACES.values()))
    ]
    missing = False
    for namespace, key in (("Person", "person_filter"), ("Event", "filter")):
        selected = args.get(key)
        if selected and not any(
            item["name"] == selected
            for group in definitions
            if group["namespace"] == namespace
            for item in group["filters"]
        ):
            missing = True
    return definitions, missing


def _apply_selected_filters(
    db_handle: DbReadBase,
    args: dict,
    namespace: str,
    handles: list[Handle],
) -> list[Handle]:
    """Intersect the named and dynamic native filters for one namespace."""
    prefix = "person_" if namespace == "Person" else ""
    for parameter in ("filter", "rules"):
        value = args.get(prefix + parameter)
        if value:
            handles = apply_filter(db_handle, {parameter: value}, namespace, handles)
    return handles


def _event_matches_type(
    event: Event, allowed_types: set[str], locale: GrampsLocale
) -> bool:
    """Match XML, Gramps, and requested-locale event type names."""
    if "all" in allowed_types:
        return True
    xml_type = event.type.xml_str()
    names = (xml_type, str(event.type), locale.translation.sgettext(xml_type))
    return any(name.strip().casefold() in allowed_types for name in names)


def _collect_anniversaries(
    db_handle: DbReadBase, args: dict, locale: GrampsLocale
) -> list[AnniversaryEvent]:
    """Walk selected subjects and their event references once."""
    db_handle = cast(DbReadBase, CacheProxyDb(db_handle))
    if args.get("anchor_gramps_id"):
        person_handles = sorted(
            _resolve_anchor_people_handles(
                db_handle, args["anchor_gramps_id"], args["generation_depth"]
            )
        )
    else:
        person_handles = cast(
            list[Handle], list(db_handle.get_person_handles(sort_handles=False))
        )
    person_handles = _apply_selected_filters(db_handle, args, "Person", person_handles)

    entries: dict[str, AnniversaryEvent] = {}
    date_components: dict[str, tuple[int, int, int] | None] = {}
    living: dict[str, bool] = {}
    people: list[Person] = []
    family_handles: set[str] = set()
    today_datetime = datetime.now(timezone.utc)
    today = Date(today_datetime.year, today_datetime.month, today_datetime.day)

    def is_living(person: Person) -> bool:
        if person.handle not in living:
            living[person.handle] = probably_alive(person, db_handle, today)
        return living[person.handle]

    def anniversary_date(event: Event) -> tuple[int, int, int] | None:
        if event.handle not in date_components:
            date_components[event.handle] = _get_anniversary_date_components(event)
        return date_components[event.handle]

    def add_reference(
        subject: Person | Family,
        event: Event,
        components: tuple[int, int, int],
        participant: str,
    ) -> None:
        object_type = "person" if isinstance(subject, Person) else "family"
        entries.setdefault(
            event.handle, AnniversaryEvent(event, components)
        ).participants[(object_type, subject.gramps_id)] = participant

    allowed_types = {
        value.strip().casefold() for value in args["event_types"] if value.strip()
    }

    for handle in person_handles:
        person = _get_record(db_handle.get_person_from_handle, handle)
        if person is None:
            continue
        people.append(person)
        family_handles.update(person.family_list)

    for family_handle in sorted(family_handles):
        family = _get_record(db_handle.get_family_from_handle, family_handle)
        if family is None:
            continue
        spouses_alive = None
        participant = None
        for reference in family.get_event_ref_list():
            role = reference.get_role()
            if args["primary_participants_only"] and not (
                role.is_primary() or role.is_family()
            ):
                continue
            event = _get_record(db_handle.get_event_from_handle, reference.ref)
            if event is None or not _event_matches_type(event, allowed_types, locale):
                continue
            components = anniversary_date(event)
            if components is None:
                continue
            if args["living_only"] and event.type != EventType.DEATH:
                if spouses_alive is None:
                    spouses = [
                        (
                            _get_record(db_handle.get_person_from_handle, parent_handle)
                            if parent_handle
                            else None
                        )
                        for parent_handle in (
                            family.father_handle,
                            family.mother_handle,
                        )
                    ]
                    spouses_alive = len(spouses) == 2 and all(
                        spouse is not None and is_living(spouse) for spouse in spouses
                    )
                if not spouses_alive:
                    continue
            if participant is None:
                participant = get_family_name_localized(family, db_handle, locale)
            add_reference(family, event, components, participant)

    for person in people:
        participant = None
        for reference in person.get_event_ref_list():
            role = reference.get_role()
            if args["primary_participants_only"] and not role.is_primary():
                continue
            event = _get_record(db_handle.get_event_from_handle, reference.ref)
            if event is None or not _event_matches_type(event, allowed_types, locale):
                continue
            components = anniversary_date(event)
            if components is None:
                continue
            if args["living_only"] and event.type != EventType.DEATH:
                if event.type == EventType.MARRIAGE or not is_living(person):
                    continue
            if participant is None:
                participant = name_displayer.display(person)
            add_reference(person, event, components, participant)

    event_handles = [
        Handle(handle)
        for handle in sorted(entries)
        if _event_matches_type(entries[handle].event, allowed_types, locale)
    ]
    event_handles = _apply_selected_filters(db_handle, args, "Event", event_handles)
    return sorted(
        (entries[handle] for handle in event_handles),
        key=lambda entry: (
            *entry.date_components[1:],
            entry.event.handle,
        ),
    )


def _validate_event_types(event_types: list[str]) -> list[str]:
    """Require the all-types selector to be used by itself."""
    normalized = {event_type.strip().casefold() for event_type in event_types}
    if "all" in normalized and normalized != {"all"}:
        raise ValidationError(
            "The 'all' event type cannot be combined with other types"
        )
    return event_types


def _build_ics(
    entries: list[AnniversaryEvent],
    tree_id: str,
    tree_name: str,
    locale: GrampsLocale = glocale,
) -> str:
    """Build ICS calendar content for a list of events."""
    translate = locale.translation.gettext
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Gramps Web//Anniversaries//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:"
        + _escape_ics_text(tree_name + " - " + translate("Anniversaries")),
        "REFRESH-INTERVAL;VALUE=DURATION:P1D",
        "X-PUBLISHED-TTL:P1D",
    ]
    for entry in entries:
        event = entry.event
        year, month, day = entry.date_components
        dtstamp = datetime.fromtimestamp(event.change or 0, timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        dtstart = f"{year:04d}{month:02d}{day:02d}"
        event_type = locale.translation.sgettext(event.type.xml_str())
        participants = ", ".join(sorted(entry.participants.values()))
        summary = f"{event_type} - {participants}" if participants else event_type
        description = _escape_ics_text(
            f"{translate('Gramps ID')}: {event.gramps_id or ''}\n"
            f"{translate('Type')}: {event_type}"
        )
        uid = _escape_ics_text(f"{event.handle}@{tree_id}.anniversaries.gramps-web")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{dtstart}",
                (
                    "RRULE:FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=-1"
                    if (month, day) == (2, 29)
                    else "RRULE:FREQ=YEARLY"
                ),
                f"SUMMARY:{_escape_ics_text(summary)}",
                f"DESCRIPTION:{description}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold_ics_line(line) for line in lines) + "\r\n"


class AnniversariesIcsQueryArgs(Schema):
    """Query arguments for GET /anniversaries.ics.

    Only exact dates with a day, month, and year are included.
    """

    token = fields.Str(
        required=True,
        validate=validate.Length(min=1),
        metadata={"description": "Persistent access token value."},
    )
    event_types = fields.DelimitedList(
        fields.Str(validate=validate.Length(min=1)),
        load_default=lambda: ["Birth", "Marriage", "Death"],
        validate=[validate.Length(min=1), _validate_event_types],
        metadata={
            "description": (
                "Comma-delimited event type names, matched case-insensitively "
                "against Gramps names and translations for the requested locale. "
                "Use 'all' by itself to include every event type."
            )
        },
    )
    living_only = fields.Bool(
        load_default=True,
        metadata={
            "description": (
                "Include non-death personal events only for living people; "
                "personal marriage events are excluded. Include non-death family "
                "events only when both spouses are known and living. Death events "
                "are not excluded."
            )
        },
    )
    primary_participants_only = fields.Bool(
        load_default=True,
        metadata={"description": "Exclude secondary participant roles."},
    )
    anchor_gramps_id = fields.Str(
        metadata={"description": "Anchor person Gramps ID for family-scope filtering."},
    )
    generation_depth = fields.Integer(
        load_default=4,
        validate=validate.Range(min=1, max=9),
        metadata={"description": "Generation depth around the anchor person."},
    )
    filter = fields.Str(
        validate=validate.Length(min=1),
        metadata={"description": "Saved Gramps Event filter name."},
    )
    rules = fields.Str(
        validate=validate.Length(min=1, max=16384),
        metadata={"description": "Gramps Event filter rules as JSON."},
    )
    person_filter = fields.Str(
        validate=validate.Length(min=1),
        metadata={"description": "Saved Gramps Person filter name."},
    )
    person_rules = fields.Str(
        validate=validate.Length(min=1, max=16384),
        metadata={"description": "Gramps Person filter rules as JSON."},
    )
    locale = fields.Str(
        load_default=None,
        validate=validate.Length(min=1, max=5),
        metadata={
            "description": "Language code used for calendar names and event text."
        },
    )


class AnniversariesIcsResource(Resource):
    """Public anniversaries ICS feed resource."""

    @api_blueprint.response(200, {"type": "string"}, content_type="text/calendar")
    @api_blueprint.alt_response(304, description="Calendar unchanged", success=True)
    @limiter.limit("300/minute")
    @limiter.limit("10/minute", key_func=_token_limit_key)
    @api_blueprint.arguments(AnniversariesIcsQueryArgs, location="query")
    def get(self, args: dict) -> Response:
        """Return exact anniversaries with a complete historical year in ICS format."""
        user = get_active_user_from_access_token(
            args["token"], ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS
        )

        tree_id = get_tree_id(str(user.id))
        if is_tree_disabled(tree=tree_id):
            abort_with_message(503, "This tree is temporarily disabled")

        permissions = get_permissions(username=user.name, tree=tree_id)
        view_private = PERM_VIEW_PRIVATE in permissions
        locale = get_locale_for_language(args["locale"], default=True)
        tree_name = get_db_manager(tree_id).name
        timestamp = get_db_last_change_timestamp(tree_id)
        filter_definitions, missing_filter = _filter_dependencies(args)
        etag = _calendar_etag(
            tree_id,
            tree_name,
            view_private,
            args,
            timestamp,
            locale,
            filter_definitions,
        )
        cache_key = f"anniversaries_ics:{etag}"
        if timestamp is not None:
            if request.if_none_match.contains_weak(etag):
                return _calendar_response("", etag)
            cached = request_cache.get(cache_key)
            if cached is not None:
                return _calendar_response(cached, etag)
        db_handle = get_db_outside_request(
            tree=tree_id,
            view_private=view_private,
            readonly=True,
            user_id=str(user.id),
        )
        try:
            events = (
                []
                if missing_filter
                else _collect_anniversaries(db_handle, args, locale)
            )
            payload = _build_ics(
                entries=events,
                tree_id=tree_id,
                tree_name=tree_name,
                locale=locale,
            )
        finally:
            close_db(db_handle)

        if timestamp is not None:
            request_cache.set(cache_key, payload, timeout=ICS_CACHE_TIMEOUT)
        else:
            etag = hashlib.sha256((etag + payload).encode()).hexdigest()
        return _calendar_response(payload, etag)
