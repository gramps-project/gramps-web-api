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
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, cast

from flask import Response, request
from flask_jwt_extended import get_jwt_identity
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db.base import DbReadBase
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.errors import HandleError
from gramps.gen.lib import Date, Event, EventType, Family, Person
from gramps.gen.lib.date import gregorian
from gramps.gen.proxy.cache import CacheProxyDb
from gramps.gen.utils.alive import probably_alive
from gramps.gen.utils.grampslocale import GrampsLocale
from marshmallow import Schema
from webargs import fields, validate

from ...auth import (
    get_name,
    get_permissions,
    get_user_details,
    get_user_from_access_token,
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
    get_tree_from_jwt_or_fail,
    get_tree_id,
)
from . import ProtectedResource, Resource
from .filters import apply_filter, get_custom_filters
from .util import get_family_name_localized

ICS_FORMAT_VERSION = 2
JSON_FORMAT_VERSION = 1
ICS_CACHE_TIMEOUT = 86400


@dataclass
class AnniversaryEvent:
    """An event and the visible participants found while collecting it."""

    event: Event
    participants: dict[tuple[str, str], str] = field(default_factory=dict)


class CalendarResponse(Response):
    """Use the complete cache validator, including permissions and arguments."""

    def make_conditional(
        self, request_or_environ, accept_ranges=False, complete_length=None
    ):
        # Compression can invoke conditional handling again. A DB timestamp
        # alone does not identify the representation selected by the query.
        environ = dict(getattr(request_or_environ, "environ", request_or_environ))
        environ.pop("HTTP_IF_MODIFIED_SINCE", None)
        return super().make_conditional(environ, accept_ranges, complete_length)


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
    format_version: int = ICS_FORMAT_VERSION,
) -> str:
    """Identify one calendar representation without opening the tree database."""
    normalized = {
        key: value.isoformat() if isinstance(value, date) else value
        for key, value in args.items()
        if key != "token"
    }
    normalized["event_types"] = sorted(
        {
            value.strip().casefold()
            for value in args.get("event_types", [])
            if value.strip()
        }
    )
    dimensions = (
        format_version,
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


def _calendar_response(
    payload: str, etag: str, timestamp: int | float | None
) -> Response:
    """Return a calendar or its conditional response with refresh headers."""
    unchanged = request.if_none_match.contains_weak(etag)
    response = CalendarResponse(
        "" if unchanged else payload,
        status=304 if unchanged else 200,
        mimetype="text/calendar",
    )
    response.headers["Content-Disposition"] = "inline; filename=anniversaries.ics"
    response.cache_control.private = True
    response.cache_control.max_age = ICS_CACHE_TIMEOUT
    response.expires = datetime.now(timezone.utc) + timedelta(seconds=ICS_CACHE_TIMEOUT)
    response.set_etag(etag, weak=True)
    if timestamp is not None:
        response.last_modified = datetime.fromtimestamp(timestamp, timezone.utc)
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


def _occurrence_dates(start: date, end: date, month: int, day: int) -> list[date]:
    """Expand one anniversary to all matching dates in an inclusive range."""
    occurrences = []
    for year in range(start.year, end.year + 1):
        occurrence_day = day
        if month == 2 and day == 29 and not _is_leap_year(year):
            occurrence_day = 28
        occurrence = date(year, month, occurrence_day)
        if start <= occurrence <= end:
            occurrences.append(occurrence)
    return occurrences


def _is_leap_year(year: int) -> bool:
    """Return whether a Gregorian year contains February 29."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _latest_calendar_end(start: date) -> date:
    """Return the inclusive upper bound five calendar years after start."""
    year = min(start.year + 5, date.max.year)
    try:
        return start.replace(year=year)
    except ValueError:
        return start.replace(year=year, day=28)


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
    definitions: list[dict[str, Any]] = [
        {
            "namespace": namespace,
            "filters": get_custom_filters({}, namespace),
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


def _apply_event_type_filter(
    db_handle: DbReadBase, event_types: list[str], handles: list[Handle]
) -> list[Handle]:
    """Use Gramps' HasType rule for the public event_types shorthand."""
    rules = {
        "function": "or",
        "rules": [
            {"name": "HasType", "values": [event_type]} for event_type in event_types
        ],
    }
    return apply_filter(db_handle, {"rules": json.dumps(rules)}, "Event", handles)


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
    events: dict[str, Event | None] = {}
    living: dict[str, bool] = {}
    people: list[Person] = []
    family_handles: set[str] = set()
    today_datetime = datetime.now(timezone.utc)
    today = Date(today_datetime.year, today_datetime.month, today_datetime.day)

    def is_living(person: Person) -> bool:
        if person.handle not in living:
            living[person.handle] = probably_alive(person, db_handle, today)
        return living[person.handle]

    def event_for(handle: str) -> Event | None:
        if handle not in events:
            events[handle] = _get_record(db_handle.get_event_from_handle, handle)
        return events[handle]

    def add_reference(
        subject: Person | Family,
        event: Event,
        participant: str,
    ) -> None:
        object_type = "person" if isinstance(subject, Person) else "family"
        entries.setdefault(event.handle, AnniversaryEvent(event)).participants[
            (object_type, subject.gramps_id)
        ] = participant

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
        spouses = [
            _get_record(db_handle.get_person_from_handle, parent_handle)
            for parent_handle in (family.father_handle, family.mother_handle)
            if parent_handle
        ]
        spouses_alive = len(spouses) == 2 and all(
            spouse is not None and is_living(spouse) for spouse in spouses
        )
        participant = None
        for reference in family.get_event_ref_list():
            role = reference.get_role()
            if args["primary_participants_only"] and not (
                role.is_primary() or role.is_family()
            ):
                continue
            event = event_for(reference.ref)
            if event is None or _get_anniversary_date_components(event) is None:
                continue
            if (
                args["living_only"]
                and event.type != EventType.DEATH
                and not spouses_alive
            ):
                continue
            if participant is None:
                participant = get_family_name_localized(family, db_handle, locale)
            add_reference(family, event, participant)

    for person in people:
        participant = None
        person_alive = is_living(person)
        for reference in person.get_event_ref_list():
            role = reference.get_role()
            if args["primary_participants_only"] and not role.is_primary():
                continue
            event = event_for(reference.ref)
            if event is None or _get_anniversary_date_components(event) is None:
                continue
            if args["living_only"] and event.type != EventType.DEATH:
                if event.type == EventType.MARRIAGE or not person_alive:
                    continue
            if participant is None:
                participant = name_displayer.display(person)
            add_reference(person, event, participant)

    event_handles = _apply_event_type_filter(
        db_handle, args["event_types"], [Handle(handle) for handle in sorted(entries)]
    )
    event_handles = _apply_selected_filters(db_handle, args, "Event", event_handles)
    return sorted(
        (entries[handle] for handle in event_handles),
        key=lambda entry: (
            *(_get_anniversary_date_components(entry.event) or (0, 0, 0))[1:],
            entry.event.handle,
        ),
    )


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
        date_components = _get_anniversary_date_components(event)
        if date_components is None:
            continue
        year, month, day = date_components
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
    """Query arguments for GET /anniversaries.ics."""

    token = fields.Str(
        required=True,
        validate=validate.Length(min=1),
        metadata={"description": "Persistent access token value."},
    )
    event_types = fields.DelimitedList(
        fields.Str(validate=validate.Length(min=1)),
        load_default=lambda: ["Birth", "Marriage", "Death"],
        validate=validate.Length(min=1),
        metadata={"description": "Comma-delimited event type names to include."},
    )
    living_only = fields.Bool(
        load_default=True,
        metadata={"description": "Limit personal events to living participants."},
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
        """Return anniversaries in ICS format."""
        user = get_user_from_access_token(
            args["token"], ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS
        )
        if user is None:
            abort_with_message(401, "Invalid access token")
        if user.role is None or user.role < 0:
            abort_with_message(403, "User account is disabled")

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
                return _calendar_response("", etag, timestamp)
            cached = request_cache.get(cache_key)
            if cached is not None:
                return _calendar_response(cached, etag, timestamp)
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
        return _calendar_response(payload, etag, timestamp)


class AnniversaryOccurrenceSchema(Schema):
    """A visible anniversary occurrence in an authenticated date range."""

    anniversary = fields.Int(required=True)
    event = fields.Dict(required=True)
    event_date = fields.Str(required=True)
    historical_date = fields.Date(required=True)
    occurrence_date = fields.Date(required=True)
    participants = fields.List(fields.Dict(), required=True)
    summary = fields.Str(required=True)
    type = fields.Str(required=True)


class AnniversariesQueryArgs(Schema):
    """Query arguments for GET /anniversaries/."""

    start = fields.Date(required=True, format="%Y-%m-%d")
    end = fields.Date(required=True, format="%Y-%m-%d")
    event_types = fields.DelimitedList(
        fields.Str(validate=validate.Length(min=1)),
        load_default=lambda: ["Birth", "Marriage", "Death"],
        validate=validate.Length(min=1),
        metadata={"description": "Comma-delimited event type names to include."},
    )
    living_only = fields.Bool(
        load_default=True,
        metadata={"description": "Limit personal events to living participants."},
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
        metadata={"description": "Language code used for localized event text."},
    )
    page = fields.Integer(load_default=1, validate=validate.Range(min=1))
    pagesize = fields.Integer(load_default=100, validate=validate.Range(min=1, max=500))


def _get_authenticated_calendar_context() -> tuple[str, str, bool]:
    """Validate the JWT user and tree before looking up cached content."""
    user_id = str(get_jwt_identity())
    try:
        username = get_name(user_id)
    except ValueError:
        abort_with_message(401, "User not found for token ID")
        raise  # mypy: unreachable
    user = get_user_details(username)
    if user is None:
        abort_with_message(401, "User not found for token ID")
        raise  # mypy: unreachable
    if user["role"] is None or user["role"] < 0:
        abort_with_message(403, "User account is disabled")

    tree_id = get_tree_from_jwt_or_fail()
    if get_tree_id(user_id) != tree_id:
        abort_with_message(403, "JWT tree does not match the user account")
    if is_tree_disabled(tree=tree_id):
        abort_with_message(503, "This tree is temporarily disabled")
    return tree_id, user_id, PERM_VIEW_PRIVATE in get_permissions(username, tree_id)


def _json_calendar_response(
    body: str, total: int, etag: str, timestamp: int | float | None
) -> Response:
    """Return JSON with private conditional-cache headers and total count."""
    unchanged = request.if_none_match.contains_weak(etag)
    response = CalendarResponse(
        "" if unchanged else body,
        status=304 if unchanged else 200,
        mimetype="application/json",
    )
    response.cache_control.private = True
    response.cache_control.max_age = ICS_CACHE_TIMEOUT
    response.expires = datetime.now(timezone.utc) + timedelta(seconds=ICS_CACHE_TIMEOUT)
    response.set_etag(etag, weak=True)
    if timestamp is not None:
        response.last_modified = datetime.fromtimestamp(timestamp, timezone.utc)
    if not unchanged:
        response.headers["X-Total-Count"] = str(total)
    return response


class AnniversariesResource(ProtectedResource):
    """Authenticated JSON occurrences for the Anniversaries page."""

    @api_blueprint.response(200, AnniversaryOccurrenceSchema(many=True))
    @api_blueprint.alt_response(304, description="Calendar unchanged", success=True)
    @api_blueprint.arguments(AnniversariesQueryArgs, location="query")
    def get(self, args: dict) -> Response:
        """Return page-sized annual occurrences in an inclusive date range."""
        if args["end"] < args["start"]:
            abort_with_message(422, "End date must not precede start date")
        if args["end"] > _latest_calendar_end(args["start"]):
            abort_with_message(422, "Date range must not exceed five years")

        tree_id, user_id, view_private = _get_authenticated_calendar_context()
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
            format_version=JSON_FORMAT_VERSION,
        )
        cache_key = f"anniversaries_json:{etag}"
        if timestamp is not None:
            if request.if_none_match.contains_weak(etag):
                return _json_calendar_response("", 0, etag, timestamp)
            cached = request_cache.get(cache_key)
            if cached is not None:
                return _json_calendar_response(
                    cached["body"], cached["total"], etag, timestamp
                )

        db_handle = get_db_outside_request(
            tree=tree_id,
            view_private=view_private,
            readonly=True,
            user_id=user_id,
        )
        try:
            entries = (
                []
                if missing_filter
                else _collect_anniversaries(db_handle, args, locale)
            )
            occurrences = []
            for entry in entries:
                components = _get_anniversary_date_components(entry.event)
                if components is None:
                    continue
                event_year, month, day = components
                event_type = locale.translation.sgettext(entry.event.type.xml_str())
                participants = [
                    {
                        "object_type": object_type,
                        "gramps_id": gramps_id,
                        "name": name,
                    }
                    for (object_type, gramps_id), name in sorted(
                        entry.participants.items()
                    )
                ]
                participant_names = ", ".join(sorted(entry.participants.values()))
                summary = (
                    f"{event_type} - {participant_names}"
                    if participant_names
                    else event_type
                )
                historical_date = date(event_year, month, day).isoformat()
                for occurrence in _occurrence_dates(
                    args["start"], args["end"], month, day
                ):
                    occurrences.append(
                        {
                            "anniversary": occurrence.year - event_year,
                            "event": {
                                "gramps_id": entry.event.gramps_id,
                                "handle": entry.event.handle,
                            },
                            "event_date": locale.date_displayer.display(
                                entry.event.date
                            ),
                            "historical_date": historical_date,
                            "occurrence_date": occurrence.isoformat(),
                            "participants": participants,
                            "summary": summary,
                            "type": event_type,
                        }
                    )
        finally:
            close_db(db_handle)

        occurrences.sort(
            key=lambda occurrence: (
                occurrence["occurrence_date"],
                occurrence["event"]["handle"],
            )
        )
        total = len(occurrences)
        offset = (args["page"] - 1) * args["pagesize"]
        body = json.dumps(
            occurrences[offset : offset + args["pagesize"]],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if timestamp is not None:
            request_cache.set(
                cache_key, {"body": body, "total": total}, timeout=ICS_CACHE_TIMEOUT
            )
        else:
            etag = hashlib.sha256((etag + body).encode()).hexdigest()
        return _json_calendar_response(body, total, etag, timestamp)
