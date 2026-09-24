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

"""Authenticated, filtered anniversary calendar subscriptions."""

import hashlib
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, cast

from flask import Response, request
from flask_jwt_extended import get_jwt_identity
from gramps.cli.clidbman import NAME_FILE
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db.base import DbReadBase
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.errors import FilterError, HandleError
from gramps.gen.lib import Date, Event, EventType, Family, Person
from gramps.gen.lib.date import gregorian
from gramps.gen.proxy.cache import CacheProxyDb
from gramps.gen.utils.alive import probably_alive
from gramps.gen.utils.grampslocale import GrampsLocale
from marshmallow import Schema, ValidationError, post_load, validates_schema
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
    get_tree_from_jwt_or_fail,
)
from . import ProtectedResource, Resource
from .filters import (
    MAX_FILTER_DEPTH,
    FilterSchema,
    apply_filter,
    get_custom_filters,
    get_rule_map,
    supports_namespace_bridge,
)
from .schemas import AnniversariesIcsQueryArgs
from .util import get_family_name_localized

ICS_FORMAT_VERSION = 2
JSON_FORMAT_VERSION = 1
ICS_CACHE_TIMEOUT = 86400


class CalendarResponse(Response):
    """Use the complete ETag, not the DB-only timestamp, for conditional requests."""

    def make_conditional(
        self, request_or_environ, accept_ranges=False, complete_length=None
    ):
        # Flask-Compress calls this after compression. Saved filters, the tree
        # name and living status can change without updating the DB timestamp.
        environ = dict(getattr(request_or_environ, "environ", request_or_environ))
        environ.pop("HTTP_IF_MODIFIED_SINCE", None)
        return super().make_conditional(environ, accept_ranges, complete_length)


@dataclass
class AnniversaryEvent:
    """An event and its already-resolved visible participants."""

    event: Event
    participants: dict[tuple[str, str], str] = field(default_factory=dict)


def _get_record(getter: Callable, handle: str):
    """Ignore dangling references and records hidden by the privacy proxy."""
    try:
        return getter(handle)
    except HandleError:
        return None


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
    """Only fully specified exact dates are anniversaries."""
    if event.date is None or not event.date.is_regular():
        return None
    date = gregorian(event.date)
    year, month, day = date.get_year(), date.get_month(), date.get_day()
    try:
        datetime(year, month, day)
    except ValueError:
        return None
    return year, month, day


def _occurrence_dates(start: date, end: date, month: int, day: int) -> list[date]:
    """Expand an anniversary to each matching date in an inclusive range."""
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
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _event_matches_type(event: Event, allowed_types: set[str]) -> bool:
    """Match canonical or server-localized event type names."""
    values = {
        str(event.type).casefold().strip(),
        event.type.xml_str().casefold().strip(),
    }
    return not values.isdisjoint(allowed_types)


def _resolve_anchor_people_handles(
    db_handle: DbReadBase,
    anchor_gramps_id: str,
    depth: int,
    direct_line: bool = False,
) -> set[str]:
    """Resolve bounded family circles, or the deprecated direct-line scope."""
    anchor = db_handle.get_person_from_gramps_id(anchor_gramps_id)
    if anchor is None:
        return set()
    selected: set[str] = set()
    # Separate walks prevent switching directions in the legacy lineage filter.
    directions = ("ancestors", "descendants") if direct_line else ("related",)
    for direction in directions:
        seen: set[str] = set()
        queue = deque([(anchor.handle, 1)])
        while queue:
            handle, level = queue.popleft()
            if handle in seen:
                continue
            seen.add(handle)
            person = _get_record(db_handle.get_person_from_handle, handle)
            if person is None:
                continue
            selected.add(handle)
            if level >= depth:
                continue
            families = []
            if direction != "descendants":
                families.extend(person.parent_family_list)
            if direction != "ancestors":
                families.extend(person.family_list)
            for family_handle in families:
                family = _get_record(db_handle.get_family_from_handle, family_handle)
                if family is None:
                    continue
                neighbors = []
                if direction != "descendants":
                    neighbors.extend([family.father_handle, family.mother_handle])
                if direction != "ancestors":
                    neighbors.extend(ref.ref for ref in family.child_ref_list)
                if direction == "related":
                    neighbors.extend([family.father_handle, family.mother_handle])
                queue.extend(
                    (neighbor, level + 1) for neighbor in neighbors if neighbor
                )
    return selected


def _validate_rules(spec: dict, namespace: str, depth: int = 0) -> None:
    """Validate names even when an empty scope or cache skips evaluation."""
    if depth >= MAX_FILTER_DEPTH:
        abort_with_message(422, "Filter nesting depth exceeded")
    for rule in spec["rules"]:
        if "name" in rule:
            rule_class = get_rule_map(namespace).get(rule["name"])
            if rule_class is None:
                abort_with_message(422, f"Unknown {namespace} filter rule")
            values = rule.get("values", [])
            if len(values) != len(rule_class.labels):
                abort_with_message(422, "Incorrect number of filter rule parameters")
            if any(not isinstance(value, (str, int, float, bool)) for value in values):
                abort_with_message(422, "Invalid filter rule parameter type")
        else:
            sub_namespace = rule.get("namespace", namespace)
            if not supports_namespace_bridge(namespace, sub_namespace):
                abort_with_message(422, "Unsupported filter namespace bridge")
            _validate_rules(rule, sub_namespace, depth + 1)


def _normalize_filters(args: dict) -> tuple[dict, list[dict], bool]:
    """Normalize cache dimensions, including saved-filter dependencies."""
    normalized = {
        key: value.isoformat() if isinstance(value, date) else value
        for key, value in args.items()
        if key != "token"
    }
    normalized["event_types"] = sorted(
        {value.strip().casefold() for value in args["event_types"]}
    )
    if not normalized["event_types"] or "" in normalized["event_types"]:
        abort_with_message(422, "At least one non-empty event type is required")
    for namespace in ("Person", "Event"):
        key = f"{namespace.lower()}_rules"
        if key in args:
            try:
                spec = FilterSchema().load(json.loads(args[key]))
            except (ValueError, ValidationError, RecursionError):
                abort_with_message(422, "Filter does not adhere to schema")
            _validate_rules(spec, namespace)
            normalized[key] = spec
    definitions: list[dict[str, Any]] = []
    missing = False
    if any(key.endswith(("_filter", "_rules")) for key in normalized):
        # Named filters may reference other filters, including other namespaces.
        for index, namespace in enumerate(sorted(set(GRAMPS_NAMESPACES.values()))):
            definitions.append(
                {
                    "namespace": namespace,
                    "filters": get_custom_filters({}, namespace, reload=index == 0),
                }
            )
        for namespace in ("Person", "Event"):
            name = args.get(f"{namespace.lower()}_filter")
            if name and not any(
                item["name"] == name
                for group in definitions
                if group["namespace"] == namespace
                for item in group["filters"]
            ):
                missing = True
    return normalized, definitions, missing


def _apply_scope_filters(
    db_handle: DbReadBase, args: dict, namespace: str, handles: list
):
    """Apply named and dynamic filters independently, by intersection."""
    prefix = namespace.lower()
    for parameter in ("filter", "rules"):
        value = args.get(f"{prefix}_{parameter}")
        if value:
            try:
                handles = apply_filter(
                    db_handle, {parameter: value}, namespace, handles
                )
            except (TypeError, ValueError, IndexError, OverflowError, FilterError):
                abort_with_message(422, "Invalid filter rule parameters")
    return handles


def _get_calendar_tree_name(tree_id: str) -> str:
    """Read the tree name without opening the database or using a stale name cache."""
    manager = get_db_manager(tree_id)
    try:
        with (Path(manager.path) / NAME_FILE).open(encoding="utf-8") as name_file:
            return name_file.readline().strip() or manager.name
    except FileNotFoundError:
        return manager.name


def _collect_anniversaries(
    db_handle: DbReadBase, args: dict, locale: GrampsLocale
) -> list[AnniversaryEvent]:
    """Walk subject references once; no event scan or per-event backlinks."""
    # Also memoize lookups made by Gramps' living-status rules and custom filters.
    db_handle = cast(DbReadBase, CacheProxyDb(db_handle))
    if args.get("anchor_gramps_id"):
        handles = sorted(
            _resolve_anchor_people_handles(
                db_handle,
                args["anchor_gramps_id"],
                args.get("generation_depth", args.get("relationship_depth", 2)),
                direct_line="generation_depth" in args,
            )
        )
    else:
        handles = list(db_handle.get_person_handles(sort_handles=False))
    handles = _apply_scope_filters(db_handle, args, "Person", handles)
    allowed_types = {value.strip().casefold() for value in args["event_types"]}
    entries: dict[str, AnniversaryEvent] = {}
    events: dict[str, Event | None] = {}
    living: dict[str, bool] = {}
    family_handles: set[str] = set()
    people: list[Person] = []
    living_marriages: set[str] = set()
    now = datetime.now(timezone.utc)
    today = Date(now.year, now.month, now.day)

    def is_living(person: Person) -> bool:
        if person.handle not in living:
            living[person.handle] = probably_alive(person, db_handle, today)
        return living[person.handle]

    def add_refs(
        subject: Person | Family, label: Callable[[], str], alive: Callable[[], bool]
    ):
        participant = None
        for ref in subject.get_event_ref_list():
            role = ref.get_role()
            if args["primary_participants_only"] and not (
                role.is_primary() or (isinstance(subject, Family) and role.is_family())
            ):
                continue
            if ref.ref not in events:
                events[ref.ref] = _get_record(db_handle.get_event_from_handle, ref.ref)
            event = events[ref.ref]
            if event is None or not _event_matches_type(event, allowed_types):
                continue
            if _get_anniversary_date_components(event) is None:
                continue
            if (
                args["living_only"]
                and event.type == EventType.MARRIAGE
                and isinstance(subject, Person)
                and ref.ref not in living_marriages
            ):
                continue
            if args["living_only"] and event.type != EventType.DEATH and not alive():
                continue
            if participant is None:
                participant = label()
            object_type = "person" if isinstance(subject, Person) else "family"
            entries.setdefault(ref.ref, AnniversaryEvent(event)).participants[
                (object_type, subject.gramps_id)
            ] = participant

    for handle in handles:
        person = _get_record(db_handle.get_person_from_handle, handle)
        if person is None:
            continue
        people.append(person)
        # Children are not primary participants in their parents' marriage.
        family_handles.update(person.family_list)
    for handle in sorted(family_handles):
        family = _get_record(db_handle.get_family_from_handle, handle)
        if family is None:
            continue
        spouses = [
            _get_record(db_handle.get_person_from_handle, parent)
            for parent in (family.father_handle, family.mother_handle)
            if parent
        ]

        def spouses_alive() -> bool:
            return len(spouses) == 2 and all(
                person is not None and is_living(person) for person in spouses
            )

        if args["living_only"]:
            for ref in family.get_event_ref_list():
                if not (ref.get_role().is_family() or ref.get_role().is_primary()):
                    continue
                if ref.ref not in events:
                    events[ref.ref] = _get_record(
                        db_handle.get_event_from_handle, ref.ref
                    )
                event = events[ref.ref]
                if (
                    event is not None
                    and event.type == EventType.MARRIAGE
                    and _event_matches_type(event, allowed_types)
                    and _get_anniversary_date_components(event) is not None
                    and spouses_alive()
                ):
                    living_marriages.add(ref.ref)
        add_refs(
            family,
            lambda: get_family_name_localized(family, db_handle, locale),
            spouses_alive,
        )
    for person in people:
        add_refs(
            person, lambda: name_displayer.display(person), lambda: is_living(person)
        )
    matched = _apply_scope_filters(db_handle, args, "Event", sorted(entries))
    return sorted(
        (entries[handle] for handle in matched),
        key=lambda entry: (
            *(_get_anniversary_date_components(entry.event) or (0, 0, 0))[1:],
            entry.event.handle,
        ),
    )


def _build_ics(
    events: list[AnniversaryEvent],
    tree_id: str,
    tree_name: str,
    locale: GrampsLocale = glocale,
) -> str:
    """Serialize a stable RFC 5545 calendar."""
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
    for entry in events:
        event = entry.event
        components = _get_anniversary_date_components(event)
        if components is None:
            continue
        year, month, day = components
        event_type = locale.translation.sgettext(event.type.xml_str())
        participants = ", ".join(sorted(entry.participants.values()))
        summary = f"{event_type} - {participants}" if participants else event_type
        description = (
            f"{translate('Gramps ID')}: {event.gramps_id or ''}\n"
            f"{translate('Type')}: {event_type}"
        )
        stamp = datetime.fromtimestamp(event.change or 0, timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        recurrence = "RRULE:FREQ=YEARLY"
        if (month, day) == (2, 29):
            recurrence += ";BYMONTH=2;BYMONTHDAY=-1"
        lines.extend(
            [
                "BEGIN:VEVENT",
                "UID:"
                + _escape_ics_text(
                    event.handle + "@" + tree_id + ".anniversaries.gramps-web"
                ),
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{year:04d}{month:02d}{day:02d}",
                recurrence,
                f"SUMMARY:{_escape_ics_text(summary)}",
                f"DESCRIPTION:{_escape_ics_text(description)}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold_ics_line(line) for line in lines) + "\r\n"


def _token_limit_key() -> str:
    """Never expose raw bearer tokens in rate-limiter storage keys."""
    return hashlib.sha256(request.args.get("token", "").encode()).hexdigest()


def _calendar_response(payload: str, etag: str, timestamp: float | None) -> Response:
    """Attach refresh and validation headers to both 200 and 304 responses."""
    response = CalendarResponse(payload, mimetype="text/calendar")
    response.headers["Content-Disposition"] = "inline; filename=anniversaries.ics"
    response.cache_control.private = True
    response.cache_control.max_age = ICS_CACHE_TIMEOUT
    response.expires = datetime.now(timezone.utc) + timedelta(seconds=ICS_CACHE_TIMEOUT)
    # Weak validators remain valid across gzip and identity representations.
    response.set_etag(etag, weak=True)
    if timestamp is not None:
        response.last_modified = timestamp
    if request.if_none_match.contains_weak(etag):
        response.status_code = 304
        response.set_data(b"")
    return response


class AnniversariesIcsResource(Resource):
    """Public anniversaries ICS feed resource."""

    @api_blueprint.response(200, {"type": "string"}, content_type="text/calendar")
    @api_blueprint.alt_response(304, description="Calendar unchanged", success=True)
    @limiter.limit("300/minute")
    @limiter.limit("10/minute", key_func=_token_limit_key)
    @api_blueprint.arguments(AnniversariesIcsQueryArgs, location="query")
    def get(self, args: dict) -> Response:
        """Return filtered yearly recurring anniversaries as an ICS calendar."""
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
        normalized, definitions, missing_filter = _normalize_filters(args)
        locale = get_locale_for_language(args.get("locale"), default=True)
        normalized["resolved_locale"] = str(locale.language)
        timestamp = get_db_last_change_timestamp(tree_id)
        tree_name = _get_calendar_tree_name(tree_id)
        dimensions = {
            "format": ICS_FORMAT_VERSION,
            "tree": tree_id,
            "timestamp": timestamp,
            "name": tree_name,
            "private": view_private,
            "args": normalized,
            "filters": definitions,
            "date": (
                datetime.now(timezone.utc).date().isoformat()
                if args["living_only"]
                else None
            ),
        }
        etag = hashlib.sha256(
            json.dumps(dimensions, sort_keys=True).encode()
        ).hexdigest()
        cache_key = f"anniversaries_ics:{etag}"
        if timestamp is not None:
            if request.if_none_match.contains_weak(etag):
                return _calendar_response("", etag, timestamp)
            cached = request_cache.get(cache_key)
            if cached is not None:
                return _calendar_response(cached, etag, timestamp)
        db_handle = get_db_outside_request(
            tree=tree_id, view_private=view_private, readonly=True, user_id=str(user.id)
        )
        try:
            events = (
                []
                if missing_filter
                else _collect_anniversaries(db_handle, args, locale)
            )
            payload = _build_ics(events, tree_id, tree_name, locale)
        finally:
            close_db(db_handle)
        if timestamp is not None:
            request_cache.set(cache_key, payload, timeout=ICS_CACHE_TIMEOUT)
        else:
            etag = hashlib.sha256((etag + payload).encode()).hexdigest()
        return _calendar_response(payload, etag, timestamp)


class AnniversaryOccurrenceSchema(Schema):
    """A visible, dated occurrence in the authenticated calendar."""

    anniversary = fields.Int(required=True)
    event = fields.Dict(required=True)
    event_date = fields.Str(required=True)
    occurrence_date = fields.Date(required=True)
    participants = fields.List(fields.Dict(), required=True)
    summary = fields.Str(required=True)
    type = fields.Str(required=True)


class AnniversariesQueryArgs(Schema):
    """Query parameters for the authenticated anniversaries view."""

    start = fields.Date(required=True, format="%Y-%m-%d")
    end = fields.Date(required=True, format="%Y-%m-%d")
    event_types = fields.DelimitedList(
        fields.Str(validate=validate.Length(min=1)),
        load_default=lambda: ["Birth", "Marriage", "Death"],
        validate=validate.Length(min=1),
    )
    living_only = fields.Bool(load_default=True)
    primary_participants_only = fields.Bool(load_default=True)
    anchor_gramps_id = fields.Str(validate=validate.Length(min=1))
    relationship_depth = fields.Int(validate=validate.Range(min=1, max=9))
    generation_depth = fields.Int(validate=validate.Range(min=1, max=9))
    person_filter = fields.Str(validate=validate.Length(min=1))
    person_rules = fields.Str(validate=validate.Length(min=1, max=16384))
    event_filter = fields.Str(validate=validate.Length(min=1))
    event_rules = fields.Str(validate=validate.Length(min=1, max=16384))
    locale = fields.Str(validate=validate.Length(min=1, max=5))
    page = fields.Int(load_default=1, validate=validate.Range(min=1))
    pagesize = fields.Int(load_default=100, validate=validate.Range(min=1, max=500))

    @validates_schema
    def validate_depth(self, data, **kwargs):
        """Prevent ambiguous legacy and family-circle scope requests."""
        if "generation_depth" in data and "relationship_depth" in data:
            raise ValidationError(
                "Choose generation_depth or relationship_depth, not both"
            )

    @post_load
    def default_depth(self, data, **kwargs):
        """Use the family-circle default unless legacy scope was requested."""
        if "generation_depth" not in data:
            data.setdefault("relationship_depth", 2)
        return data


def _get_authenticated_calendar_context() -> tuple[str, str, bool]:
    """Validate the current user and tree before an anniversary cache lookup."""
    user_id = get_jwt_identity()
    try:
        username = get_name(user_id)
    except ValueError:
        abort_with_message(401, "User not found for token ID")
        raise  # mypy; unreachable
    user = get_user_details(username)
    if user is None:
        abort_with_message(401, "User not found for token ID")
        raise  # mypy; unreachable
    if user["role"] is None or user["role"] < 0:
        abort_with_message(403, "User account is disabled")
    tree_id = get_tree_from_jwt_or_fail()
    if get_tree_id(user_id) != tree_id:
        abort_with_message(403, "JWT tree does not match the user account")
    if is_tree_disabled(tree=tree_id):
        abort_with_message(503, "This tree is temporarily disabled")
    return tree_id, user_id, PERM_VIEW_PRIVATE in get_permissions(username, tree_id)


def _calendar_cache_dimensions(
    tree_id: str, view_private: bool, args: dict, format_version: int
) -> tuple[str, float | None, bool, object]:
    """Return a stable cache validator and the resolved locale for one request."""
    normalized, definitions, missing_filter = _normalize_filters(args)
    locale = get_locale_for_language(args.get("locale"), default=True)
    normalized["resolved_locale"] = str(locale.language)
    dimensions = {
        "format": format_version,
        "tree": tree_id,
        "timestamp": get_db_last_change_timestamp(tree_id),
        "private": view_private,
        "args": normalized,
        "filters": definitions,
        "date": (
            datetime.now(timezone.utc).date().isoformat()
            if args["living_only"]
            else None
        ),
    }
    timestamp = dimensions["timestamp"]
    etag = hashlib.sha256(json.dumps(dimensions, sort_keys=True).encode()).hexdigest()
    return etag, timestamp, missing_filter, locale


def _json_calendar_response(
    body: str, total: int, etag: str, timestamp: float | None
) -> Response:
    """Build JSON with the same conditional-cache contract as the ICS feed."""
    unchanged = request.if_none_match.contains_weak(etag)
    response = Response(
        "" if unchanged else body,
        status=304 if unchanged else 200,
        mimetype="application/json",
    )
    response.cache_control.private = True
    response.cache_control.max_age = ICS_CACHE_TIMEOUT
    response.expires = datetime.now(timezone.utc) + timedelta(seconds=ICS_CACHE_TIMEOUT)
    response.set_etag(etag, weak=True)
    if timestamp is not None:
        response.last_modified = timestamp
    if not unchanged:
        response.headers["X-Total-Count"] = str(total)
    return response


class AnniversariesResource(ProtectedResource):
    """Authenticated JSON occurrences for the standalone Anniversaries page."""

    @api_blueprint.response(200, AnniversaryOccurrenceSchema(many=True))
    @api_blueprint.alt_response(304, description="Calendar unchanged", success=True)
    @api_blueprint.arguments(AnniversariesQueryArgs, location="query")
    def get(self, args: dict) -> Response:
        """Return page-sized annual occurrences in an inclusive date range."""
        if args["end"] < args["start"]:
            abort_with_message(422, "End date must not precede start date")
        if (args["end"] - args["start"]).days > 5 * 366:
            abort_with_message(422, "Date range must not exceed five years")

        tree_id, user_id, view_private = _get_authenticated_calendar_context()
        etag, timestamp, missing_filter, locale = _calendar_cache_dimensions(
            tree_id, view_private, args, JSON_FORMAT_VERSION
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
            user_id=str(user_id),
        )
        try:
            events = (
                []
                if missing_filter
                else _collect_anniversaries(db_handle, args, locale)
            )
            occurrences = []
            for entry in events:
                components = _get_anniversary_date_components(entry.event)
                if components is None:
                    continue
                event_year, month, day = components
                event_type = locale.translation.sgettext(entry.event.type.xml_str())
                participant_values = [
                    {
                        "object_type": object_type,
                        "gramps_id": gramps_id,
                        "name": name,
                    }
                    for (object_type, gramps_id), name in sorted(
                        entry.participants.items()
                    )
                ]
                summary = ", ".join(sorted(entry.participants.values()))
                if summary:
                    summary = f"{event_type} - {summary}"
                else:
                    summary = event_type
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
                            "occurrence_date": occurrence.isoformat(),
                            "participants": participant_values,
                            "summary": summary,
                            "type": event_type,
                        }
                    )
        finally:
            close_db(db_handle)

        occurrences.sort(
            key=lambda occurrence: (
                occurrence["occurrence_date"],
                occurrence["type"],
                occurrence["event"]["handle"],
            )
        )
        total = len(occurrences)
        offset = (args["page"] - 1) * args["pagesize"]
        body = json.dumps(
            occurrences[offset : offset + args["pagesize"]],
            ensure_ascii=False,
            sort_keys=True,
        )
        if timestamp is not None:
            request_cache.set(
                cache_key, {"body": body, "total": total}, timeout=ICS_CACHE_TIMEOUT
            )
        else:
            etag = hashlib.sha256((etag + body).encode()).hexdigest()
        return _json_calendar_response(body, total, etag, timestamp)
