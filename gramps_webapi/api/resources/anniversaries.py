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
from flask_jwt_extended import get_jwt, get_jwt_identity
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
    get_name,
    get_permissions,
    get_user_details,
    is_tree_disabled,
)
from ...auth.const import (
    ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS,
    PERM_VIEW_OTHER_TREE,
    PERM_VIEW_PRIVATE,
)
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
    get_tree_from_jwt,
    get_tree_id,
)
from . import ProtectedResource, Resource
from .access_tokens import get_active_user_from_access_token
from .filters import apply_filter, get_custom_filters
from .schemas import AnniversaryOccurrenceSchema
from .util import get_family_name_localized

# Bump this when the ICS representation changes so old server cache entries expire.
ICS_FORMAT_VERSION = 3
JSON_FORMAT_VERSION = 1
ICS_CACHE_TIMEOUT = 86400
# RFC 5545 requires a full DATE; leap year 2000 also represents yearless Feb 29.
ICS_PLACEHOLDER_YEAR = 2000
# Representative source-calendar years near Gregorian 2000 for yearless conversion.
ICS_SOURCE_REFERENCE_YEARS = {
    Date.CAL_GREGORIAN: 2000,
    Date.CAL_JULIAN: 2000,
    Date.CAL_HEBREW: 5760,
    Date.CAL_PERSIAN: 1378,
    Date.CAL_FRENCH: 208,
    Date.CAL_ISLAMIC: 1420,
    Date.CAL_SWEDISH: 2000,
}


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
    format_version: int = ICS_FORMAT_VERSION,
    excluded_args: frozenset[str] = frozenset(),
) -> str:
    """Identify the feed without opening the tree database."""
    normalized = {
        key: value
        for key, value in args.items()
        if key != "token" and key not in excluded_args
    }
    for key, value in normalized.items():
        if isinstance(value, date):
            normalized[key] = value.isoformat()
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
    """Return exact Gregorian components; year 0 represents an unknown year."""
    if event.date is None:
        return None

    source_date = event.date
    year_is_unknown = source_date.get_year() == 0
    if year_is_unknown:
        source_date = Date(source_date)
        reference_year = ICS_SOURCE_REFERENCE_YEARS.get(source_date.get_calendar())
        if reference_year is None:
            return None
        source_date.set_year(reference_year)
    if not source_date.is_regular():
        return None

    event_date = gregorian(source_date)
    year, month, day = (
        event_date.get_year(),
        event_date.get_month(),
        event_date.get_day(),
    )
    if year_is_unknown:
        year = 0
    try:
        # Validate month/day using the ICS placeholder when Gramps has no year.
        datetime(year or ICS_PLACEHOLDER_YEAR, month, day)
    except ValueError:
        return None
    return year, month, day


def _latest_calendar_end(start: date) -> date:
    """Return the inclusive upper bound five calendar years after start."""
    year = min(start.year + 5, date.max.year)
    try:
        return start.replace(year=year)
    except ValueError:
        # A leap-day start has no matching date in a non-leap target year.
        return start.replace(year=year, day=28)


def _occurrence_dates(
    start: date, end: date, event_year: int, month: int, day: int
) -> list[date]:
    """Expand one exact anniversary to occurrences in an inclusive range."""
    occurrences = []
    for year in range(start.year, end.year + 1):
        if event_year and year < event_year:
            continue
        occurrence_day = day
        try:
            occurrence = date(year, month, occurrence_day)
        except ValueError:
            if month != 2 or day != 29:
                continue
            occurrence = date(year, month, 28)
        if start <= occurrence <= end:
            occurrences.append(occurrence)
    return occurrences


def _localized_event_summary(
    entry: AnniversaryEvent, locale: GrampsLocale
) -> tuple[str, str]:
    """Return the translated event type and participant-aware summary."""
    event_type = locale.translation.sgettext(entry.event.type.xml_str())
    participants = ", ".join(sorted(entry.participants.values()))
    summary = f"{event_type} - {participants}" if participants else event_type
    return event_type, summary


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
        year_is_unknown = year == 0
        ics_year = ICS_PLACEHOLDER_YEAR if year_is_unknown else year
        dtstamp = datetime.fromtimestamp(event.change or 0, timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        dtstart = f"{ics_year:04d}{month:02d}{day:02d}"
        event_type, summary = _localized_event_summary(entry, locale)
        description_lines = [
            f"{translate('Gramps ID')}: {event.gramps_id or ''}",
            f"{translate('Type')}: {event_type}",
        ]
        if year_is_unknown:
            description_lines.append(
                translate(
                    "The year is not recorded; 2000 is only a technical "
                    "placeholder for the yearly recurrence."
                )
            )
        description = _escape_ics_text("\n".join(description_lines))
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


class AnniversariesQueryArgs(Schema):
    """Query parameters shared by the ICS feed and JSON occurrences endpoint."""

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


class AnniversariesIcsQueryArgs(AnniversariesQueryArgs):
    """Query arguments for GET /anniversaries.ics."""

    token = fields.Str(
        required=True,
        validate=validate.Length(min=1),
        metadata={"description": "Persistent access token value."},
    )


class AnniversariesJsonQueryArgs(AnniversariesQueryArgs):
    """Query arguments for GET /anniversaries/."""

    start = fields.Date(
        required=True,
        format="%Y-%m-%d",
        metadata={"description": "First included occurrence date (YYYY-MM-DD)."},
    )
    end = fields.Date(
        required=True,
        format="%Y-%m-%d",
        metadata={"description": "Last included occurrence date (YYYY-MM-DD)."},
    )
    page = fields.Integer(
        load_default=1,
        validate=validate.Range(min=1),
        metadata={"description": "One-based page number."},
    )
    pagesize = fields.Integer(
        load_default=100,
        validate=validate.Range(min=1, max=500),
        metadata={"description": "Number of occurrences per page (1 to 500)."},
    )
    tree = fields.Str(
        load_default=None,
        validate=[
            validate.Length(min=1),
            validate.Regexp(r"^[a-zA-Z0-9_-]+$"),
        ],
        metadata={
            "description": (
                "Tree ID to select in multi-tree mode; requires permission to view other trees."
            )
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
        """Return exact anniversaries; missing years use 2000 as an ICS placeholder."""
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


def _get_authenticated_calendar_context(
    requested_tree: str | None,
) -> tuple[str, str, bool]:
    """Resolve and validate the current JWT user's tree and effective access."""
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

    jwt_tree = get_tree_from_jwt()
    tree_id = requested_tree or jwt_tree
    if not tree_id:
        abort_with_message(403, "No tree ID in JWT or request")
        raise  # mypy: unreachable
    current_permissions = get_permissions(username, tree_id)
    jwt_permissions = set(get_jwt().get("permissions", []))
    effective_permissions = current_permissions & jwt_permissions
    user_tree = user.get("tree")
    if user_tree != tree_id and PERM_VIEW_OTHER_TREE not in effective_permissions:
        abort_with_message(403, "Not authorized to view this tree")
    if is_tree_disabled(tree=tree_id):
        abort_with_message(503, "This tree is temporarily disabled")

    return (
        tree_id,
        user_id,
        PERM_VIEW_PRIVATE in effective_permissions,
    )


def _json_page_etag(base_etag: str, page: int, pagesize: int) -> str:
    """Make pagination part of the representation validator."""
    dimensions = (base_etag, page, pagesize)
    return hashlib.sha256(json.dumps(dimensions).encode()).hexdigest()


def _json_calendar_response(
    body: str, total: int, etag: str, unchanged: bool = False
) -> Response:
    """Return private JSON with conditional-cache headers and a total count."""
    response = Response(
        "" if unchanged else body,
        status=304 if unchanged else 200,
        mimetype="application/json",
    )
    response.cache_control.private = True
    response.cache_control.max_age = ICS_CACHE_TIMEOUT
    response.expires = datetime.now(timezone.utc) + timedelta(seconds=ICS_CACHE_TIMEOUT)
    response.set_etag(etag, weak=True)
    if not unchanged:
        response.headers["X-Total-Count"] = str(total)
    return response


class AnniversariesResource(ProtectedResource):
    """Authenticated JSON occurrences for an inclusive date range."""

    @api_blueprint.response(
        200,
        AnniversaryOccurrenceSchema(many=True),
        headers={
            "X-Total-Count": {
                "description": "Total matching occurrences across all pages.",
                "schema": {"type": "integer"},
            }
        },
    )
    @api_blueprint.alt_response(304, description="Occurrences unchanged", success=True)
    @api_blueprint.arguments(AnniversariesJsonQueryArgs, location="query")
    def get(self, args: dict) -> Response:
        """Return annual anniversary occurrences in the requested date range."""
        if args["end"] < args["start"]:
            abort_with_message(422, "End date must not precede start date")
        if args["end"] > _latest_calendar_end(args["start"]):
            abort_with_message(422, "Date range must not exceed five years")

        tree_id, user_id, view_private = _get_authenticated_calendar_context(
            args.get("tree")
        )
        locale = get_locale_for_language(args["locale"], default=True)
        try:
            tree_name = get_db_manager(tree_id).name
        except ValueError:
            abort_with_message(404, "Tree not found")
            raise  # mypy: unreachable
        timestamp = get_db_last_change_timestamp(tree_id)
        filter_definitions, missing_filter = _filter_dependencies(args)
        base_etag = _calendar_etag(
            tree_id,
            tree_name,
            view_private,
            args,
            timestamp,
            locale,
            filter_definitions,
            format_version=JSON_FORMAT_VERSION,
            excluded_args=frozenset({"page", "pagesize", "tree"}),
        )
        etag = _json_page_etag(base_etag, args["page"], args["pagesize"])
        cache_key = f"anniversaries_json:{base_etag}"

        if timestamp is not None:
            if request.if_none_match.contains_weak(etag):
                return _json_calendar_response("", 0, etag, unchanged=True)
            occurrences = request_cache.get(cache_key)
        else:
            occurrences = None

        if occurrences is None:
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
                    event_year, month, day = entry.date_components
                    event_type, summary = _localized_event_summary(entry, locale)
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
                    historical_date = (
                        date(event_year, month, day).isoformat() if event_year else None
                    )
                    event_date = locale.date_displayer.display(entry.event.date)
                    for occurrence in _occurrence_dates(
                        args["start"],
                        args["end"],
                        event_year,
                        month,
                        day,
                    ):
                        occurrences.append(
                            {
                                "anniversary": (
                                    occurrence.year - event_year if event_year else None
                                ),
                                "event": {
                                    "handle": entry.event.handle,
                                    "gramps_id": entry.event.gramps_id,
                                },
                                "event_date": event_date,
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
            if timestamp is not None:
                request_cache.set(cache_key, occurrences, timeout=ICS_CACHE_TIMEOUT)

        total = len(occurrences)
        offset = (args["page"] - 1) * args["pagesize"]
        page_items = occurrences[offset : offset + args["pagesize"]]
        body = json.dumps(page_items, ensure_ascii=False, sort_keys=True)
        if timestamp is None:
            etag = hashlib.sha256(
                json.dumps(
                    (base_etag, args["page"], args["pagesize"], total, body)
                ).encode()
            ).hexdigest()
        return _json_calendar_response(body, total, etag)
