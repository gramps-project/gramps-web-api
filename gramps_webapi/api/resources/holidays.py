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

"""Holidays API resource."""

from typing import Dict

from flask import Response, abort
from gramps.plugins.lib.libholiday import HolidayTable

from ..util import use_args
from . import ProtectedResource
from .emit import GrampsJSONEncoder


class HolidaysResource(ProtectedResource, GrampsJSONEncoder):
    """Holidays resource."""

    @use_args({}, location="query")
    def get(self, args: Dict) -> Response:
        """Get list of countries that have holiday calendars."""
        holidays = HolidayTable()
        return self.response(200, holidays.get_countries())


class HolidayResource(ProtectedResource, GrampsJSONEncoder):
    """Holiday resource."""

    @use_args({}, location="query")
    def get(
        self,
        args: Dict,
        country: str = None,
        year: int = None,
        month: int = None,
        day: int = None,
    ) -> Response:
        """If the given day is a holiday return the name or names."""
        holidays = HolidayTable()
        holidays.load_holidays(year, country)
        name = holidays.get_holidays(1, 1)
        if name == []:
            abort(404)
        try:
            name = holidays.get_holidays(month, day)
        except KeyError:
            abort(422)
        return self.response(200, name)
