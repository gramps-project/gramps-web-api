#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
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

"""Timeline API resources."""
from typing import Dict, List, Optional, Set, Tuple, Union

from flask import abort
from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db.base import DbReadBase
from gramps.gen.display.place import PlaceDisplay
from gramps.gen.errors import HandleError
from gramps.gen.lib import Date, Event, EventType, Person, Span
from gramps.gen.relationship import get_relationship_calculator
from gramps.gen.utils.alive import probably_alive_range
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
from ...const import NAME_FORMAT_REGEXP
from .util import (
    get_person_profile_for_object,
    get_place_profile_for_object,
    get_rating,
)

pd = PlaceDisplay()
default_locale = GrampsLocale(lang="en")
event_type = EventType()

DEATH_INDICATORS = [
    event_type.DEATH,
    event_type.BURIAL,
    event_type.CREMATION,
    event_type.CAUSE_DEATH,
    event_type.PROBATE,
]

RELATIVES = [
    "father",
    "mother",
    "brother",
    "sister",
    "wife",
    "husband",
    "son",
    "daughter",
]

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
# (Event, Person, relationship)
#
# A timeline may or may not have a anchor person. If it does relationships
# are calculated with respect to them.


class Timeline:
    """Timeline class."""

    def __init__(
        self,
        db_handle: DbReadBase,
        dates: Optional[str] = None,
        events: Optional[List[str]] = None,
        ratings: bool = False,
        relatives: Optional[List[str]] = None,
        relative_events: Optional[List[str]] = None,
        discard_empty: bool = True,
        omit_anchor: bool = True,
        precision: int = 1,
        locale: GrampsLocale = glocale,
        name_format: Optional[str] = None,
    ):
        """Initialize timeline."""
        self.db_handle = db_handle
        self.timeline: List[Tuple[Event, Person, str, str]] = []
        self.dates = dates
        self.start_date = None
        self.end_date = None
        self.ratings = ratings
        self.discard_empty = discard_empty
        self.precision = precision
        self.locale = locale
        self.anchor_person = None
        self.omit_anchor = omit_anchor
        self.depth = 1
        self.eligible_events: Set[str] = set()
        self.event_filters: List[str] = events or []
        self.eligible_relative_events: Set[str] = set()
        self.relative_event_filters: List[str] = relative_events or []
        self.relative_filters: List[str] = relatives or []
        self.set_event_filters(self.event_filters)
        self.set_relative_event_filters(self.relative_event_filters)
        self.birth_dates: Dict[str, Date] = {}
        self.name_format = name_format

        if dates and "-" in dates:
            start, end = dates.split("-")
            if "/" in start:
                year, month, day = start.split("/")
                self.start_date = Date((int(year), int(month), int(day)))
            else:
                self.start_date = None
            if "/" in end:
                year, month, day = end.split("/")
                self.end_date = Date((int(year), int(month), int(day)))
            else:
                self.end_date = None

    def set_start_date(self, date: Union[Date, str]):
        """Set optional timeline start date."""
        if isinstance(date, str):
            year, month, day = date.split("/")
            self.start_date = Date((int(year), int(month), int(day)))
        else:
            self.start_date = date

    def set_end_date(self, date: Union[Date, str]):
        """Set optional timeline end date."""
        if isinstance(date, str):
            year, month, day = date.split("/")
            self.end_date = Date((int(year), int(month), int(day)))
        else:
            self.end_date = date

    def set_discard_empty(self, discard_empty: bool):
        """Set discard empty identifier."""
        self.discard_empty = discard_empty

    def set_precision(self, precision: int):
        """Set optional precision for span."""
        self.precision = precision

    def set_locale(self, locale: str):
        """Set optional locale for span."""
        self.locale = get_locale_for_language(locale, default=True)

    def set_event_filters(self, filters: Optional[List[str]] = None):
        """Prepare the event filter table."""
        self.event_filters = filters or []
        self.eligible_events = self._prepare_eligible_events(self.event_filters)

    def set_relative_event_filters(self, filters: Optional[List[str]] = None):
        """Prepare the relative event filter table."""
        self.relative_event_filters = filters or []
        self.eligible_relative_events = self._prepare_eligible_events(
            self.relative_event_filters
        )

    def _prepare_eligible_events(self, event_filters: List[str]):
        """Prepare an event filter list."""
        eligible_events = {"Birth", "Death"}
        event_type = EventType()
        default_event_types = event_type.get_standard_xml()
        default_event_map = event_type.get_map()
        custom_event_types = self.db_handle.get_event_types()
        for key in event_filters:
            if key in default_event_types:
                eligible_events.add(key)
                continue
            if key in custom_event_types:
                eligible_events.add(key)
                continue
            if key not in EVENT_CATEGORIES:
                raise ValueError(f"{key} is not a valid event or event category")
        for entry in event_type.get_menu_standard_xml():
            event_key = entry[0].lower().replace("life events", "vital")
            if event_key in event_filters:
                for event_id in entry[1]:
                    if event_id in default_event_map:
                        eligible_events.add(default_event_map[event_id])
                break
        if "custom" in event_filters:
            for event_name in custom_event_types:
                eligible_events.add(event_name)
        return eligible_events

    def get_age(self, start_date: str, date: str):
        """Return calculated age or empty string otherwise."""
        age = ""
        if start_date:
            span = Span(start_date, date)
            if span.is_valid():
                age = str(
                    span.format(precision=self.precision, dlocale=self.locale).strip(
                        "()"
                    )
                )
        return age

    def is_death_indicator(self, event: Event) -> bool:
        """Check if an event indicates death timeframe."""
        if event.type in DEATH_INDICATORS:
            return True
        for event_name in [
            "Funeral",
            "Interment",
            "Reinterment",
            "Inurnment",
            "Memorial",
            "Visitation",
            "Wake",
            "Shiva",
        ]:
            if self.locale.translation.sgettext(event_name) == str(event.type):
                return True
        return False

    def is_eligible(self, event: Event, relative: bool):
        """Check if an event is eligible for the timeline."""
        if relative:
            if self.relative_event_filters == []:
                return True
            return str(event.get_type()) in self.eligible_relative_events
        if self.event_filters == []:
            return True
        return str(event.get_type()) in self.eligible_events

    def add_event(self, event: Tuple[Event, Person, str, str], relative: bool = False):
        """Add event to timeline if needed."""
        if self.discard_empty:
            if event[0].date.sortval == 0:
                return
        if self.end_date:
            if self.end_date.match(event[0].date, comparison="<"):
                return
        if self.start_date:
            if self.start_date.match(event[0].date, comparison=">"):
                return
        for item in self.timeline:
            if item[0].handle == event[0].handle:
                return
        if self.is_eligible(event[0], relative):
            if self.ratings:
                count, confidence = get_rating(self.db_handle, event[0])
                event[0].citations = count
                event[0].confidence = confidence
            self.timeline.append(event)

    def add_person(
        self,
        handle: Handle,
        anchor: bool = False,
        start: bool = True,
        end: bool = True,
        ancestors: int = 1,
        offspring: int = 1,
    ):
        """Add events for a person to the timeline."""
        if self.anchor_person and handle == self.anchor_person.handle:
            return
        person = self.db_handle.get_person_from_handle(handle)
        if person.handle not in self.birth_dates:
            event = get_birth_or_fallback(self.db_handle, person)
            if event:
                self.birth_dates.update({person.handle: event.date})
        for event_ref in person.event_ref_list:
            event = self.db_handle.get_event_from_handle(event_ref.ref)
            role = event_ref.get_role().xml_str()
            self.add_event((event, person, "self", role))
        if anchor and not self.anchor_person:
            self.anchor_person = person
            self.depth = max(ancestors, offspring) + 1
            if self.start_date is None and self.end_date is None:
                if len(self.timeline) > 0:
                    if start or end:
                        self.timeline.sort(
                            key=lambda x: x[0].get_date_object().get_sort_value()
                        )
                        if start:
                            self.start_date = self.timeline[0][0].date
                        if end:
                            if self.is_death_indicator(self.timeline[-1][0]):
                                self.end_date = self.timeline[-1][0].date
                            else:
                                data = probably_alive_range(person, self.db_handle)
                                self.end_date = data[1]

            for family in person.parent_family_list:
                self.add_family(family, ancestors=ancestors)

            for family in person.family_list:
                self.add_family(
                    family, anchor=person, ancestors=ancestors, offspring=offspring
                )
        else:
            for family in person.family_list:
                self.add_family(family, anchor=person, events_only=True)

    def add_relative(self, handle: Handle, ancestors: int = 1, offspring: int = 1):
        """Add events for a relative of the anchor person."""
        person = self.db_handle.get_person_from_handle(handle)
        calculator = get_relationship_calculator(reinit=True, clocale=self.locale)
        calculator.set_depth(self.depth)
        relationship = calculator.get_one_relationship(
            self.db_handle, self.anchor_person, person
        )
        if self.relative_filters:
            found = False
            for relative in self.relative_filters:
                if relative in relationship:
                    found = True
                    break
            if not found:
                return

        if self.relative_event_filters:
            for event_ref in person.event_ref_list:
                event = self.db_handle.get_event_from_handle(event_ref.ref)
                role = event_ref.get_role().xml_str()
                self.add_event((event, person, relationship, role), relative=True)

        event = get_birth_or_fallback(self.db_handle, person)
        if event:
            self.add_event((event, person, relationship, "Primary"), relative=True)
            if person.handle not in self.birth_dates:
                self.birth_dates.update({person.handle: event.date})

        event = get_death_or_fallback(self.db_handle, person)
        if event:
            self.add_event((event, person, relationship, "Primary"), relative=True)

        for family_handle in person.family_list:
            family = self.db_handle.get_family_from_handle(family_handle)

            event = get_marriage_or_fallback(self.db_handle, family)
            if event:
                self.add_event((event, person, relationship, "Family"), relative=True)

            event = get_divorce_or_fallback(self.db_handle, family)
            if event:
                self.add_event((event, person, relationship, "Family"), relative=True)

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
        anchor: Optional[Person] = None,
        include_children: bool = True,
        ancestors: int = 1,
        offspring: int = 1,
        events_only: bool = False,
    ):
        """Add events for all family members to the timeline."""
        family = self.db_handle.get_family_from_handle(handle)
        if anchor:
            for event_ref in family.event_ref_list:
                event = self.db_handle.get_event_from_handle(event_ref.ref)
                role = event_ref.get_role().xml_str()
                self.add_event((event, anchor, "self", role))
            if events_only:
                return
        if self.anchor_person:
            if (
                family.father_handle
                and family.father_handle != self.anchor_person.handle
            ):
                self.add_relative(family.father_handle, ancestors=ancestors)
            if (
                family.mother_handle
                and family.mother_handle != self.anchor_person.handle
            ):
                self.add_relative(family.mother_handle, ancestors=ancestors)
            if include_children:
                for child in family.child_ref_list:
                    if child.ref != self.anchor_person.handle:
                        self.add_relative(child.ref, offspring=offspring)
        else:
            if family.father_handle:
                self.add_person(family.father_handle)
            if family.mother_handle:
                self.add_person(family.mother_handle)
            for child in family.child_ref_list:
                self.add_person(child.ref)

    def profile(self, page=0, pagesize=20):
        """Return a profile for the timeline."""
        profiles = []
        self.timeline.sort(key=lambda x: x[0].get_date_object().get_sort_value())
        events = self.timeline
        if page > 0:
            offset = (page - 1) * pagesize
            events = events[offset : offset + pagesize]
        for event, person_object, relationship, role in events:
            label = self.locale.translation.sgettext(str(event.type))
            if (
                person_object
                and self.anchor_person
                and self.anchor_person.handle != person_object.handle
                and relationship not in ["self", "", None]
            ):
                label = f"{label} ({self.locale.translation.sgettext(relationship.title())})"

            try:
                obj = self.db_handle.get_place_from_handle(event.place)
                place = get_place_profile_for_object(
                    self.db_handle, obj, locale=self.locale
                )
                place["display_name"] = pd.display_event(self.db_handle, event)
                place["handle"] = event.place
            except HandleError:
                place = {}

            age = ""
            person = {}
            if person_object is not None:
                person_age = ""
                get_person = True
                if self.anchor_person:
                    if self.anchor_person.handle in self.birth_dates:
                        age = self.get_age(
                            self.birth_dates[self.anchor_person.handle], event.date
                        )
                    if self.anchor_person.handle == person_object.handle:
                        person_age = age
                        if self.omit_anchor:
                            get_person = False
                if get_person:
                    person = get_person_profile_for_object(
                        self.db_handle,
                        person_object,
                        [],
                        locale=self.locale,
                        name_format=self.name_format,
                    )
                    if not person_age and person_object.handle in self.birth_dates:
                        person_age = self.get_age(
                            self.birth_dates[person_object.handle], event.date
                        )
                        if not age:
                            age = person_age
                    person["age"] = person_age
            date_format = config.get("preferences.date-format")
            self.locale.date_displayer.set_format(date_format)
            profile = {
                "date": self.locale.date_displayer.display(event.date),
                "description": event.description,
                "gramps_id": event.gramps_id,
                "handle": event.handle,
                "label": label,
                "media": [x.ref for x in event.media_list],
                "person": person,
                "place": place,
                "age": age,
                "type": event.type,
                "role": self.locale.translation.gettext(role),
            }
            profile["person"]["relationship"] = str(relationship)
            if self.ratings:
                profile["citations"] = event.citations
                profile["confidence"] = event.confidence
            profiles.append(profile)
        return profiles


def prepare_events(args: Dict):
    """Prepare events list."""
    events = []
    if "events" in args:
        events = args["events"]
    if "event_classes" in args:
        events = events + args["event_classes"]
    return events


class PersonTimelineResource(ProtectedResource, GrampsJSONEncoder):
    """Person timeline resource."""

    @use_args(
        {
            "ancestors": fields.Integer(
                load_default=1, validate=validate.Range(min=1, max=5)
            ),
            "dates": fields.Str(
                load_default=None,
                validate=validate.Regexp(
                    r"^-[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])$|"
                    r"^[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])-$|"
                    r"^[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])-"
                    r"[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])$"
                ),
            ),
            "discard_empty": fields.Boolean(load_default=True),
            "event_classes": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(choices=EVENT_CATEGORIES),
            ),
            "events": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "first": fields.Boolean(load_default=True),
            "keys": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "last": fields.Boolean(load_default=True),
            "locale": fields.Str(load_default=None),
            "name_format": fields.Str(validate=validate.Regexp(NAME_FORMAT_REGEXP)),
            "offspring": fields.Integer(
                load_default=1, validate=validate.Range(min=1, max=5)
            ),
            "omit_anchor": fields.Boolean(load_default=True),
            "page": fields.Integer(load_default=0, validate=validate.Range(min=1)),
            "pagesize": fields.Integer(load_default=20, validate=validate.Range(min=1)),
            "precision": fields.Integer(
                load_default=1, validate=validate.Range(min=1, max=3)
            ),
            "ratings": fields.Boolean(load_default=False),
            "relative_event_classes": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(choices=EVENT_CATEGORIES),
            ),
            "relative_events": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
            ),
            "relatives": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(choices=RELATIVES),
            ),
            "skipkeys": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "strip": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def get(self, args: Dict, handle: str):
        """Get list of events in timeline for a person."""
        locale = get_locale_for_language(args["locale"], default=True)
        events = prepare_events(args)
        relatives = []
        if "relatives" in args:
            relatives = args["relatives"]
        relative_events = []
        if "relative_events" in args:
            relative_events = args["relative_events"]
        if "relative_event_classes" in args:
            relative_events = relative_events + args["relative_event_classes"]
        try:
            timeline = Timeline(
                get_db_handle(),
                dates=args["dates"],
                events=events,
                ratings=args["ratings"],
                relatives=relatives,
                relative_events=relative_events,
                discard_empty=args["discard_empty"],
                omit_anchor=args["omit_anchor"],
                precision=args["precision"],
                locale=locale,
            )
            timeline.add_person(
                Handle(handle),
                anchor=True,
                start=args["first"],
                end=args["last"],
                ancestors=args["ancestors"],
                offspring=args["offspring"],
            )
        except ValueError:
            abort(422)
        except HandleError:
            abort(404)

        payload = timeline.profile(page=args["page"], pagesize=args["pagesize"])
        return self.response(200, payload, args, total_items=len(timeline.timeline))


class FamilyTimelineResource(ProtectedResource, GrampsJSONEncoder):
    """Family timeline resource."""

    @use_args(
        {
            "dates": fields.Str(
                load_default=None,
                validate=validate.Regexp(
                    r"^-[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])$|"
                    r"^[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])-$|"
                    r"^[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])-"
                    r"[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])$"
                ),
            ),
            "discard_empty": fields.Boolean(load_default=True),
            "event_classes": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(choices=EVENT_CATEGORIES),
            ),
            "events": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "keys": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "locale": fields.Str(load_default=None),
            "name_format": fields.Str(validate=validate.Regexp(NAME_FORMAT_REGEXP)),
            "page": fields.Integer(load_default=0, validate=validate.Range(min=1)),
            "pagesize": fields.Integer(load_default=20, validate=validate.Range(min=1)),
            "ratings": fields.Boolean(load_default=False),
            "skipkeys": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "keys": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "strip": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def get(self, args: Dict, handle: str):
        """Get list of events in timeline for a family."""
        locale = get_locale_for_language(args["locale"], default=True)
        events = prepare_events(args)
        try:
            timeline = Timeline(
                get_db_handle(),
                dates=args["dates"],
                events=events,
                ratings=args["ratings"],
                discard_empty=args["discard_empty"],
                locale=locale,
                name_format=args.get("name_format"),
            )
            timeline.add_family(Handle(handle))
        except ValueError:
            abort(422)
        except HandleError:
            abort(404)

        payload = timeline.profile(page=args["page"], pagesize=args["pagesize"])
        return self.response(200, payload, args, total_items=len(timeline.timeline))


class TimelinePeopleResource(ProtectedResource, GrampsJSONEncoder):
    """People timeline resource."""

    @use_args(
        {
            "anchor": fields.Str(validate=validate.Length(min=1)),
            "dates": fields.Str(
                load_default=None,
                validate=validate.Regexp(
                    r"^-[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])$|"
                    r"^[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])-$|"
                    r"^[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])-"
                    r"[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])$"
                ),
            ),
            "discard_empty": fields.Boolean(load_default=True),
            "event_classes": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(choices=EVENT_CATEGORIES),
            ),
            "events": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "filter": fields.Str(validate=validate.Length(min=1)),
            "first": fields.Boolean(load_default=True),
            "handles": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "keys": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "last": fields.Boolean(load_default=True),
            "locale": fields.Str(
                load_default=None, validate=validate.Length(min=1, max=5)
            ),
            "omit_anchor": fields.Boolean(load_default=True),
            "page": fields.Integer(load_default=0, validate=validate.Range(min=1)),
            "pagesize": fields.Integer(load_default=20, validate=validate.Range(min=1)),
            "precision": fields.Integer(
                load_default=1, validate=validate.Range(min=1, max=3)
            ),
            "ratings": fields.Boolean(load_default=False),
            "rules": fields.Str(validate=validate.Length(min=1)),
            "skipkeys": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "strip": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def get(self, args: Dict):
        """Get consolidated list of events in timeline for a list of people."""
        db_handle = get_db_handle()
        locale = get_locale_for_language(args["locale"], default=True)
        events = prepare_events(args)
        try:
            timeline = Timeline(
                db_handle,
                dates=args["dates"],
                events=events,
                ratings=args["ratings"],
                discard_empty=args["discard_empty"],
                omit_anchor=args["omit_anchor"],
                precision=args["precision"],
                locale=locale,
                name_format=args.get("name_format"),
            )
            if "anchor" in args:
                timeline.add_person(
                    args["anchor"], anchor=True, start=args["first"], end=args["last"]
                )

            if "handles" in args:
                handles = args["handles"]
            else:
                handles = db_handle.get_person_handles(sort_handles=True, locale=locale)

            if "filter" in args or "rules" in args:
                handles = apply_filter(db_handle, args, "Person", handles)

            if "anchor" in args:
                for handle in handles:
                    timeline.add_relative(handle)
            else:
                for handle in handles:
                    timeline.add_person(handle)
        except ValueError:
            abort(422)
        except HandleError:
            abort(404)

        payload = timeline.profile(page=args["page"], pagesize=args["pagesize"])
        return self.response(200, payload, args, total_items=len(timeline.timeline))


class TimelineFamiliesResource(ProtectedResource, GrampsJSONEncoder):
    """Families timeline resource."""

    @use_args(
        {
            "dates": fields.Str(
                load_default=None,
                validate=validate.Regexp(
                    r"^-[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])$|"
                    r"^[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])-$|"
                    r"^[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])-"
                    r"[0-9]+/([1-9]|1[0-2])/([1-9]|1[0-9]|2[0-9]|3[0-1])$"
                ),
            ),
            "discard_empty": fields.Boolean(load_default=True),
            "event_classes": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1)),
                validate=validate.ContainsOnly(choices=EVENT_CATEGORIES),
            ),
            "events": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "filter": fields.Str(validate=validate.Length(min=1)),
            "keys": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "handles": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "locale": fields.Str(
                load_default=None, validate=validate.Length(min=1, max=5)
            ),
            "page": fields.Integer(load_default=0, validate=validate.Range(min=1)),
            "pagesize": fields.Integer(load_default=20, validate=validate.Range(min=1)),
            "ratings": fields.Boolean(load_default=False),
            "rules": fields.Str(validate=validate.Length(min=1)),
            "skipkeys": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "strip": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def get(self, args: Dict):
        """Get consolidated list of events in timeline for a list of families."""
        db_handle = get_db_handle()
        locale = get_locale_for_language(args["locale"], default=True)
        events = prepare_events(args)
        try:
            timeline = Timeline(
                db_handle,
                dates=args["dates"],
                events=events,
                ratings=args["ratings"],
                discard_empty=args["discard_empty"],
                locale=locale,
                name_format=args.get("name_format"),
            )
        except ValueError:
            abort(422)

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

        payload = timeline.profile(page=args["page"], pagesize=args["pagesize"])
        return self.response(200, payload, args, total_items=len(timeline.timeline))
