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
from datetime import datetime, timedelta, timezone
from typing import Optional

from flask import Response, request
from gramps.gen.lib import Event
from gramps.gen.lib.date import gregorian
from marshmallow import Schema
from webargs import fields, validate

from ...auth import (
    get_permissions,
    is_tree_disabled,
)
from ...auth.const import ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS, PERM_VIEW_PRIVATE
from ..blueprint import api_blueprint
from ..cache import get_db_last_change_timestamp, request_cache
from ..ratelimiter import limiter
from ..util import (
    abort_with_message,
    close_db,
    get_db_outside_request,
    get_tree_id,
)
from . import Resource
from .access_tokens import get_active_user_from_access_token
from .filters import apply_filter
from .util import get_backlinks, get_event_summary_from_object

ICS_FORMAT_VERSION = 2
ICS_CACHE_TIMEOUT = 86400


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


def _calendar_etag(tree_id: str, view_private: bool, args: dict, timestamp) -> str:
    """Identify the feed without opening the tree database."""
    normalized = {key: value for key, value in args.items() if key != "token"}
    normalized["event_types"] = sorted(
        {
            value.strip().casefold()
            for value in args.get("event_types", [])
            if value.strip()
        }
    )
    dimensions = (ICS_FORMAT_VERSION, tree_id, timestamp, view_private, normalized)
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
    """Escape text fields according to RFC 5545."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _event_matches_type(event: Event, allowed_types: set[str]) -> bool:
    """Check if an event type matches one of the requested filters."""
    if not allowed_types:
        return True
    event_values = {
        str(event.get_type()).casefold().strip(),
        event.get_type().xml_str().casefold().strip(),
    }
    return not event_values.isdisjoint(allowed_types)


def _get_anniversary_date_components(event: Event) -> Optional[tuple[int, int, int]]:
    """Get Gregorian (year, month, day) tuple for an event date."""
    if event.date is None or not event.date.is_valid():
        return None
    gdate = gregorian(event.date)
    month = gdate.get_month()
    day = gdate.get_day()
    if month < 1 or day < 1:
        return None
    year = gdate.get_year()
    if year < 1:
        year = 1970
    if year > 9999:
        year = 9999
    return year, month, day


def _is_event_in_anchor_scope(
    db_handle,
    event: Event,
    allowed_people: set[str],
    allowed_families: set[str],
) -> bool:
    """Check if an event is linked to people/families in anchor scope."""
    backlinks = get_backlinks(db_handle, event.handle)
    people = set(backlinks.get("person", []))
    if not people.isdisjoint(allowed_people):
        return True
    families = set(backlinks.get("family", []))
    return not families.isdisjoint(allowed_families)


def _resolve_anchor_people_handles(
    db_handle, anchor_gramps_id: str, generation_depth: int
) -> set[str]:
    """Resolve people handles to include for an anchor+generation filter."""
    anchor = db_handle.get_person_from_gramps_id(anchor_gramps_id)
    if anchor is None:
        abort_with_message(404, "Anchor person not found")
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
    handles = db_handle.get_person_handles(sort_handles=True)
    return set(
        apply_filter(
            db_handle,
            {"rules": json.dumps(rules)},
            "Person",
            handles,
        )
    )


def _resolve_family_handles_for_people(db_handle, people_handles: set[str]) -> set[str]:
    """Resolve families attached to in-scope people handles."""
    family_handles = set()
    for handle in people_handles:
        person = db_handle.get_person_from_handle(handle)
        if person is None:
            continue
        family_handles.update(person.family_list)
        family_handles.update(person.parent_family_list)
    return family_handles


def _build_ics(events: list[Event], db_handle, tree_id: str) -> str:
    """Build ICS calendar content for a list of events."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Gramps Web//Anniversaries//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Gramps Anniversaries",
        "REFRESH-INTERVAL;VALUE=DURATION:P1D",
        "X-PUBLISHED-TTL:P1D",
    ]
    for event in events:
        date_components = _get_anniversary_date_components(event)
        if date_components is None:
            continue
        year, month, day = date_components
        dtstamp = datetime.fromtimestamp(event.change or 0, timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        dtstart = f"{year:04d}{month:02d}{day:02d}"
        summary = _escape_ics_text(get_event_summary_from_object(db_handle, event))
        description = _escape_ics_text(
            f"Gramps ID: {event.gramps_id or ''}\nType: {event.get_type().xml_str()}"
        )
        uid = _escape_ics_text(f"{event.handle}@{tree_id}.anniversaries.gramps-web")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{dtstart}",
                "RRULE:FREQ=YEARLY",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _event_sort_key(event: Event) -> tuple[int, int, int, str]:
    """Return stable sort key for anniversary events."""
    date_components = _get_anniversary_date_components(event)
    if date_components is None:
        return (12, 31, 9999, event.handle)
    year, month, day = date_components
    return (month, day, year, event.handle)


class AnniversariesIcsQueryArgs(Schema):
    """Query arguments for GET /anniversaries.ics."""

    token = fields.Str(
        required=True,
        validate=validate.Length(min=1),
        metadata={"description": "Persistent access token value."},
    )
    event_types = fields.DelimitedList(
        fields.Str(validate=validate.Length(min=1)),
        metadata={"description": "Comma-delimited event type names to include."},
    )
    anchor_gramps_id = fields.Str(
        metadata={"description": "Anchor person Gramps ID for family-scope filtering."},
    )
    generation_depth = fields.Integer(
        load_default=4,
        validate=validate.Range(min=1, max=9),
        metadata={"description": "Generation depth around the anchor person."},
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
        user = get_active_user_from_access_token(
            args["token"], ACCESS_TOKEN_SCOPE_ANNIVERSARIES_ICS
        )

        tree_id = get_tree_id(str(user.id))
        if is_tree_disabled(tree=tree_id):
            abort_with_message(503, "This tree is temporarily disabled")

        permissions = get_permissions(username=user.name, tree=tree_id)
        view_private = PERM_VIEW_PRIVATE in permissions
        timestamp = get_db_last_change_timestamp(tree_id)
        etag = _calendar_etag(tree_id, view_private, args, timestamp)
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
            iter_event_handles = db_handle.method("iter_event_handles")
            get_event_from_handle = db_handle.method("get_event_from_handle")
            if iter_event_handles is None:
                raise RuntimeError("Method iter_event_handles not found")
            if get_event_from_handle is None:
                raise RuntimeError("Method get_event_from_handle not found")

            allowed_types = {
                event_type.casefold().strip()
                for event_type in args.get("event_types", [])
                if event_type and event_type.strip()
            }

            anchor_gramps_id = args.get("anchor_gramps_id")
            allowed_people = set()
            allowed_families = set()
            if anchor_gramps_id:
                allowed_people = _resolve_anchor_people_handles(
                    db_handle, anchor_gramps_id, args["generation_depth"]
                )
                allowed_families = _resolve_family_handles_for_people(
                    db_handle, allowed_people
                )

            events = []
            for handle in iter_event_handles():
                event = get_event_from_handle(handle)
                if event is None:
                    continue
                if not _event_matches_type(event, allowed_types):
                    continue
                if _get_anniversary_date_components(event) is None:
                    continue
                if anchor_gramps_id and not _is_event_in_anchor_scope(
                    db_handle, event, allowed_people, allowed_families
                ):
                    continue
                events.append(event)

            events.sort(key=_event_sort_key)
            payload = _build_ics(events=events, db_handle=db_handle, tree_id=tree_id)
        finally:
            close_db(db_handle)

        if timestamp is not None:
            request_cache.set(cache_key, payload, timeout=ICS_CACHE_TIMEOUT)
        else:
            etag = hashlib.sha256((etag + payload).encode()).hexdigest()
        return _calendar_response(payload, etag, timestamp)
