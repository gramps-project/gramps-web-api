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

"""Matching utilities."""
from typing import List

from gramps.gen.db.base import DbReadBase
from gramps.gen.lib import Date
from gramps.gen.lib.date import gregorian

from ...types import Handle


def match_date(date: Date, mask: str) -> bool:
    """Check if date matches mask."""
    if date is not None and date.is_valid():
        year_mask, month_mask, day_mask = mask.split("/")
        date = gregorian(date)
        year = date.get_year()
        if year_mask == "*" or year == int(year_mask):
            month = date.get_month()
            if month_mask == "*" or month == int(month_mask):
                day = date.get_day()
                if day_mask == "*" or day == int(day_mask):
                    return True
    return False


def match_date_range(date: Date, start_date: Date, end_date: Date) -> bool:
    """Check if date falls in given range."""
    if start_date:
        if start_date.match(date, comparison=">"):
            return False
    if end_date:
        if end_date.match(date, comparison="<"):
            return False
    return True


def match_dates(
    db_handle: DbReadBase, gramps_class_name: str, handles: List[Handle], date_mask: str
):
    """Match dates based on a date mask or range."""
    check_range = False
    if "-" in date_mask:
        check_range = True
        start, end = date_mask.split("-")
        if "/" in start:
            year, month, day = start.split("/")
            start_date = Date((int(year), int(month), int(day)))
        else:
            start_date = None
        if "/" in end:
            year, month, day = end.split("/")
            end_date = Date((int(year), int(month), int(day)))
        else:
            end_date = None

    query_method = db_handle.method("get_%s_from_handle", gramps_class_name)
    result = []
    for handle in handles:
        obj = query_method(handle)
        date = obj.get_date_object()
        if date.is_valid():
            if check_range:
                if match_date_range(date, start_date, end_date):
                    result.append(handle)
            else:
                if match_date(date, date_mask):
                    result.append(handle)
    return result
