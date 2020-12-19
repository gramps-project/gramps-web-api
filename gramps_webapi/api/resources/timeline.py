#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
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

"""Timeline collection functions."""
from typing import Dict, List, Tuple, Union

from flask import abort
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db.base import DbReadBase
from gramps.gen.display.place import PlaceDisplay
from gramps.gen.errors import HandleError
from gramps.gen.lib import Date, Event, EventType, Person, Span
from gramps.gen.relationship import get_relationship_calculator
from gramps.gen.utils.db import (
    get_birth_or_fallback,
    get_death_or_fallback,
    get_divorce_or_fallback,
    get_marriage_or_fallback,
)
from gramps.gen.utils.grampslocale import GrampsLocale
from webargs import fields, validate

from ...types import Handle
from ..util import get_db_handle, get_locale_for_language, use_args
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .filters import apply_filter
from .util import get_person_profile_for_object, get_place_profile_for_object

pd = PlaceDisplay()

EVENT_CATEGORIES = [
    "vital",
    "family",
    "religious",
    "vocational",
    "academic",
    "travel",
    "legal",
    "residence",
    "other",
    "custom",
]


# A timeline item is a tuple of following format:
#
# (Event, Person, relationship, span)
#
# A timeline may or may not have a focal person. If it does relationships
# are calculated with respect to them and the span represents the age
# of the focal person at the time of the event.


class Timeline:
    """Timeline class."""

    def __init__(
        self,
        db_handle: DbReadBase,
        events: Union[List, None] = None,
        relative_events: Union[List, None] = None,
        discard_empty: bool = True,
        omit_focal: bool = True,
        precision: int = 1,
        locale: GrampsLocale = glocale,
    ):
        """Initialize timeline."""
        self.db_handle = db_handle
        self.timeline = []
        self.start_date = None
        self.end_date = None
        self.discard_empty = discard_empty
        self.precision = precision
        self.locale = locale
        self.focal_person = None
        self.omit_focal = omit_focal
        self.eligible_events = []
        self.event_filters = events or []
        self.eligible_relative_events = []
        self.relative_event_filters = relative_events or []
        self.set_event_filters(self.event_filters)
        self.set_relative_event_filters(self.relative_event_filters)

    def set_start_date(self, date: Date):
        """Set optional timeline start date."""
        self.start_date = date

    def set_end_date(self, date: Date):
        """Set optional timeline end date."""
        self.start_date = date

    def set_discard_empty(self, discard_empty: bool):
        """Set discard empty identifier."""
        self.discard_empty = discard_empty

    def set_precision(self, precision: int):
        """Set optional precision for span."""
        self.precision = precision

    def set_locale(self, locale: str):
        """Set optional locale for span."""
        self.locale = get_locale_for_language(locale, default=True)

    def set_event_filters(self, filters: Union[List, None] = None):
        """Prepare the event filter table."""
        self.event_filters = filters or []
        self.eligible_events = self._prepare_eligible_events(self.event_filters)

    def set_relative_event_filters(self, filters: Union[List, None] = None):
        """Prepare the relative event filter table."""
        self.relative_event_filters = filters or []
        self.eligible_relative_events = self._prepare_eligible_events(
            self.relative_event_filters
        )

    def _prepare_eligible_events(self, event_filters: List):
        """Prepare an event filter list."""
        eligible_events = []
        event_type = EventType()
        for entry in event_type.get_menu_standard_xml():
            event_key = entry[0].lower().replace("life events", "vital")
            for key in event_filters:
                if key == event_key:
                    eligible_events = eligible_events + entry[1]
                    break
        if "custom" in event_filters:
            eligible_events.append(event_type.CUSTOM)
        if event_type.BIRTH not in eligible_events:
            eligible_events.append(event_type.BIRTH)
        if event_type.DEATH not in eligible_events:
            eligible_events.append(event_type.DEATH)
        return eligible_events

    def is_eligible(self, event: Event, relative: bool):
        """Check if an event is eligible for the timeline."""
        if relative:
            return int(event.get_type()) in self.eligible_relative_events
        if self.event_filters == []:
            return True
        return int(event.get_type()) in self.eligible_events

    def add_event(self, event: Tuple, relative=False):
        """Add event to timeline if needed."""
        if self.discard_empty:
            if event[0].date.sortval == 0:
                return
        if self.end_date:
            if self.end_date.match(event[0].date, comparison="<"):
                return
        span = ""
        if self.start_date:
            if self.start_date.match(event[0].date, comparison=">"):
                return
            span = str(
                Span(self.start_date, event[0].date)
                .format(precision=self.precision, dlocale=self.locale)
                .strip("()")
            )
        for item in self.timeline:
            if item[0].handle == event[0].handle:
                return
        if self.is_eligible(event[0], relative):
            self.timeline.append(event + (span,))

    def add_person(
        self,
        handle: Handle,
        focal: bool = False,
        start: bool = True,
        end: bool = True,
        ancestors: int = 1,
        offspring: int = 1,
    ):
        """Add events for a person to the timeline."""
        if self.focal_person and handle == self.focal_person.handle:
            return
        person = self.db_handle.get_person_from_handle(handle)
        for event_ref in person.event_ref_list:
            event = self.db_handle.get_event_from_handle(event_ref.ref)
            self.add_event((event, person, "self"))
        if focal and not self.focal_person:
            self.focal_person = person
            if len(self.timeline) > 0:
                if start or end:
                    self.timeline.sort(
                        key=lambda x: x[0].get_date_object().get_sort_value()
                    )
                    if start:
                        self.start_date = self.timeline[0][0].date
                    if end:
                        self.end_date = self.timeline[-1][0].date

            for family in person.family_list:
                self.add_family(
                    family, focal=person, ancestors=ancestors, offspring=offspring
                )

            for family in person.parent_family_list:
                self.add_family(family, ancestors=ancestors)

    def add_relative(self, handle: Handle, ancestors: int = 1, offspring: int = 1):
        """Add events for a relative of the focal person."""
        person = self.db_handle.get_person_from_handle(handle)
        calculator = get_relationship_calculator(reinit=True, clocale=self.locale)
        relationship = calculator.get_one_relationship(
            self.db_handle, self.focal_person, person
        )

        if self.relative_event_filters == []:
            for event_ref in person.event_ref_list:
                event = self.db_handle.get_event_from_handle(event_ref.ref)
                self.add_event((event, person, relationship), relative=True)

        event = get_birth_or_fallback(self.db_handle, person)
        if event:
            self.add_event((event, person, relationship))

        event = get_death_or_fallback(self.db_handle, person)
        if event:
            self.add_event((event, person, relationship))

        for family_handle in person.family_list:
            family = self.db_handle.get_family_from_handle(family_handle)

            event = get_marriage_or_fallback(self.db_handle, family)
            if event:
                self.add_event((event, person, relationship))

            event = get_divorce_or_fallback(self.db_handle, family)
            if event:
                self.add_event((event, person, relationship))

            if offspring > 1:
                for child_ref in family.child_ref_list:
                    self.add_relative(child_ref.ref, offspring=offspring - 1)

        if ancestors > 1:
            if "father" in relationship or "mother" in relationship:
                for family_handle in person.parent_family_list:
                    self.add_family(
                        family_handle, include_children=False, ancestors=ancestors - 1
                    )

    def add_family(
        self,
        handle: Handle,
        focal: Union[Person, None] = None,
        include_children: bool = True,
        ancestors: int = 1,
        offspring: int = 1,
    ):
        """Add events for all family members to the timeline."""
        family = self.db_handle.get_family_from_handle(handle)
        if focal:
            for event_ref in family.event_ref_list:
                event = self.db_handle.get_event_from_handle(event_ref.ref)
                self.add_event((event, focal, "self"))
        if self.focal_person:
            if (
                family.father_handle
                and family.father_handle != self.focal_person.handle
            ):
                self.add_relative(family.father_handle, ancestors=ancestors)
            if (
                family.mother_handle
                and family.mother_handle != self.focal_person.handle
            ):
                self.add_relative(family.mother_handle, ancestors=ancestors)
            if include_children:
                for child in family.child_ref_list:
                    if child.ref != self.focal_person.handle:
                        self.add_relative(child.ref, offspring=offspring)
        else:
            if family.father_handle:
                self.add_person(family.father_handle)
            if family.mother_handle:
                self.add_person(family.mother_handle)
            for child in family.child_ref_list:
                self.add_person(child.ref)

    @property
    def profile(self):
        """Return a profile for the timeline."""
        profiles = []
        self.timeline.sort(key=lambda x: x[0].get_date_object().get_sort_value())
        for event in self.timeline:
            label = self.locale.translation.sgettext(str(event[0].type))
            if (
                event[1]
                and self.focal_person
                and self.focal_person.handle != event[1].handle
                and event[2] not in ["self", "", None]
            ):
                label = "{} of {}".format(label, event[2].title())
            try:
                obj = self.db_handle.get_place_from_handle(event[0].place)
                place = get_place_profile_for_object(
                    self.db_handle, obj, locale=self.locale
                )
                place["display_name"] = pd.display_event(self.db_handle, event[0])
                place["handle"] = event[0].place
            except HandleError:
                place = {}
            person = {}
            if event[1] is not None:
                if self.focal_person and self.focal_person.handle == event[1].handle:
                    if not self.omit_focal:
                        person = get_person_profile_for_object(
                            self.db_handle, event[1], {}
                        )
                else:
                    person = get_person_profile_for_object(self.db_handle, event[1], {})
            profile = {
                "date": self.locale.date_displayer.display(event[0].date),
                "description": event[0].description,
                "gramps_id": event[0].gramps_id,
                "handle": event[0].handle,
                "label": self.locale.translation.sgettext(label),
                "media": [x.ref for x in event[0].media_list],
                "person": person,
                "place": place,
                "span": event[3],
                "type": event[0].type,
            }
            profile["person"]["relationship"] = str(event[2])
            profiles.append(profile)
        return profiles


class PersonTimelineResource(ProtectedResource, GrampsJSONEncoder):
    """Person timeline resource."""

    @use_args(
        {
            "ancestors": fields.Integer(
                missing=1, validate=validate.Range(min=1, max=5)
            ),
            "discard_empty": fields.Boolean(missing=True),
            "events": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(choices=EVENT_CATEGORIES),
            ),
            "first": fields.Boolean(missing=True),
            "keys": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "last": fields.Boolean(missing=True),
            "locale": fields.Str(missing=None),
            "offspring": fields.Integer(
                missing=1, validate=validate.Range(min=1, max=5)
            ),
            "omit_focal": fields.Boolean(missing=True),
            "precision": fields.Integer(missing=1),
            "relative_events": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(choices=EVENT_CATEGORIES),
            ),
            "skipkeys": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "strip": fields.Boolean(missing=False),
        },
        location="query",
    )
    def get(self, args: Dict, handle: str):
        """Get list of events in timeline for a person."""
        locale = get_locale_for_language(args["locale"], default=True)
        event_filters = []
        if "events" in args:
            event_filters = args["events"]
        relative_event_filters = []
        if "relative_events" in args:
            relative_event_filters = args["relative_events"]
        timeline = Timeline(
            get_db_handle(),
            events=event_filters,
            relative_events=relative_event_filters,
            discard_empty=args["discard_empty"],
            omit_focal=args["omit_focal"],
            precision=args["precision"],
            locale=locale,
        )
        try:
            timeline.add_person(
                handle,
                focal=True,
                start=args["first"],
                end=args["last"],
                ancestors=args["ancestors"],
                offspring=args["offspring"],
            )
        except HandleError:
            abort(404)
        return self.response(200, timeline.profile, args)


class FamilyTimelineResource(ProtectedResource, GrampsJSONEncoder):
    """Family timeline resource."""

    @use_args(
        {
            "discard_empty": fields.Boolean(missing=True),
            "events": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(choices=EVENT_CATEGORIES),
            ),
            "keys": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "locale": fields.Str(missing=None),
            "skipkeys": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "strip": fields.Boolean(missing=False),
        },
        location="query",
    )
    def get(self, args: Dict, handle: str):
        """Get list of events in timeline for a family."""
        locale = get_locale_for_language(args["locale"], default=True)
        event_filters = []
        if "events" in args:
            event_filters = args["events"]
        timeline = Timeline(
            get_db_handle(),
            events=event_filters,
            discard_empty=args["discard_empty"],
            locale=locale,
        )
        try:
            timeline.add_family(handle)
        except HandleError:
            abort(404)
        return self.response(200, timeline.profile, args)


class TimelinePeopleResource(ProtectedResource, GrampsJSONEncoder):
    """People timeline resource."""

    @use_args(
        {
            "discard_empty": fields.Boolean(missing=True),
            "events": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(choices=EVENT_CATEGORIES),
            ),
            "filter": fields.Str(validate=validate.Length(min=1)),
            "first": fields.Boolean(missing=True),
            "focal": fields.Str(validate=validate.Length(min=1)),
            "handles": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "keys": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "last": fields.Boolean(missing=True),
            "locale": fields.Str(missing=None, validate=validate.Length(min=1, max=5)),
            "omit_focal": fields.Boolean(missing=True),
            "precision": fields.Integer(missing=1),
            "relative_events": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(choices=EVENT_CATEGORIES),
            ),
            "rules": fields.Str(validate=validate.Length(min=1)),
            "skipkeys": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "strip": fields.Boolean(missing=False),
        },
        location="query",
    )
    def get(self, args: Dict):
        """Get consolidated list of events in timeline for a list of people."""
        db_handle = get_db_handle()
        locale = get_locale_for_language(args["locale"], default=True)
        event_filters = []
        if "events" in args:
            event_filters = args["events"]
        relative_event_filters = []
        if "relative_events" in args:
            relative_event_filters = args["relative_events"]
        timeline = Timeline(
            db_handle,
            events=event_filters,
            relative_events=relative_event_filters,
            discard_empty=args["discard_empty"],
            omit_focal=args["omit_focal"],
            precision=args["precision"],
            locale=locale,
        )
        try:
            if "focal" in args:
                timeline.add_person(
                    args["focal"], focal=True, start=args["first"], end=args["last"]
                )

            if "handles" in args:
                handles = args["handles"]
            else:
                handles = db_handle.get_person_handles(sort_handles=True, locale=locale)

            if "filter" in args or "rules" in args:
                handles = apply_filter(db_handle, args, "Person", handles)

            if "focal" in args:
                for handle in handles:
                    timeline.add_relative(handle)
            else:
                for handle in handles:
                    timeline.add_person(handle)
        except HandleError:
            abort(404)
        return self.response(200, timeline.profile, args)


class TimelineFamiliesResource(ProtectedResource, GrampsJSONEncoder):
    """Families timeline resource."""

    @use_args(
        {
            "discard_empty": fields.Boolean(missing=True),
            "events": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(choices=EVENT_CATEGORIES),
            ),
            "filter": fields.Str(validate=validate.Length(min=1)),
            "keys": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "handles": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "locale": fields.Str(missing=None, validate=validate.Length(min=1, max=5)),
            "rules": fields.Str(validate=validate.Length(min=1)),
            "skipkeys": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "strip": fields.Boolean(missing=False),
        },
        location="query",
    )
    def get(self, args: Dict):
        """Get consolidated list of events in timeline for a list of families."""
        db_handle = get_db_handle()
        locale = get_locale_for_language(args["locale"], default=True)
        event_filters = []
        if "events" in args:
            event_filters = args["events"]
        timeline = Timeline(
            db_handle,
            events=event_filters,
            discard_empty=args["discard_empty"],
            locale=locale,
        )

        if "handles" in args:
            handles = args["handles"]
        else:
            handles = db_handle.get_family_handles(sort_handles=True, locale=locale)

        try:
            if "filter" in args or "rules" in args:
                handles = apply_filter(db_handle, args, "Family", handles)

            for handle in handles:
                timeline.add_family(handle)
        except HandleError:
            abort(404)
        return self.response(200, timeline.profile, args)