#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Event API resource."""

from typing import Dict

from flask import Response, abort
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib import Event, Span
from gramps.gen.utils.grampslocale import GrampsLocale
from webargs import fields, validate

from ...types import Handle
from ..util import abort_with_message, get_db_handle, get_locale_for_language, use_args
from . import ProtectedResource
from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .emit import GrampsJSONEncoder
from .util import (
    get_event_profile_for_object,
    get_extended_attributes,
    get_place_by_handle,
)


class EventResourceHelper(GrampsObjectResourceHelper):
    """Event resource helper."""

    gramps_class_name = "Event"

    def object_extend(
        self, obj: Event, args: Dict, locale: GrampsLocale = glocale
    ) -> Event:
        """Extend event attributes as needed."""
        db_handle = self.db_handle
        if "extend" in args:
            obj.extended = get_extended_attributes(db_handle, obj, args)
            if "all" in args["extend"] or "place" in args["extend"]:
                obj.extended["place"] = get_place_by_handle(db_handle, obj.place)
        if "profile" in args:
            if "families" in args["profile"] or "events" in args["profile"]:
                abort_with_message(422, "profile contains invalid keys")
            obj.profile = get_event_profile_for_object(
                db_handle,
                obj,
                args["profile"],
                locale=locale,
                name_format=args.get("name_format"),
            )
        return obj


class EventResource(GrampsObjectProtectedResource, EventResourceHelper):
    """Event resource."""


class EventsResource(GrampsObjectsProtectedResource, EventResourceHelper):
    """Events resource."""


class EventSpanResource(ProtectedResource, GrampsJSONEncoder):
    """Event date span resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_db_handle()

    @use_args(
        {
            "as_age": fields.Boolean(load_default=True),
            "locale": fields.Str(
                load_default=None, validate=validate.Length(min=1, max=5)
            ),
            "precision": fields.Integer(
                load_default=2, validate=validate.Range(min=1, max=3)
            ),
        },
        location="query",
    )
    def get(self, args: Dict, handle1: Handle, handle2: Handle) -> Response:
        """Get the time span between two event dates."""
        try:
            event1 = self.db_handle.get_event_from_handle(handle1)
            event2 = self.db_handle.get_event_from_handle(handle2)
        except HandleError:
            abort(404)

        locale = get_locale_for_language(args["locale"], default=True)
        span = (
            Span(event1.date, event2.date)
            .format(precision=args["precision"], as_age=args["as_age"], dlocale=locale)
            .strip("()")
        )
        return self.response(200, {"span": str(span)})
