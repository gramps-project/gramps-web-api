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

"""Gramps Json Encoder."""

from typing import Any, Dict, Optional

import gramps.gen.lib as lib
from flask import Response, current_app, json
from gramps.gen.db import DbBookmarks
from gramps.gen.lib.baseobj import BaseObject
from werkzeug.datastructures import Headers


def default(obj: Any):
    """Default handler for unserializable objects."""
    current_app.logger.error("Unexpected object type: " + obj.__class__.__name__)
    return None


class GrampsJSONEncoder:
    """Customizes Gramps Web API output."""

    gramps_class_name = ""

    def __init__(self):
        """Initialize class."""
        self.strip_empty_keys = False
        self.filter_only_keys = []
        self.filter_skip_keys = []

    def response(
        self,
        status: int = 200,
        payload: Optional[Any] = None,
        args: Optional[Dict] = None,
        total_items: int = -1,
    ) -> Response:
        """Prepare response."""
        if payload is None:
            payload = {}
        args = args or {}
        if "strip" in args:
            self.strip_empty_keys = args["strip"]
        else:
            self.strip_empty_keys = False
        if "keys" in args:
            self.filter_only_keys = args["keys"]
        else:
            self.filter_only_keys = []
        if "skipkeys" in args:
            self.filter_skip_keys = args["skipkeys"]
        else:
            self.filter_skip_keys = []

        if total_items > -1:
            headers = Headers()
            headers.add("X-Total-Count", total_items)
        else:
            headers = None

        return Response(
            status=status,
            headers=headers,
            response=json.dumps(
                self.extract_objects(payload),
                ensure_ascii=False,
                sort_keys=True,
                default=default,
            ),
            mimetype="application/json",
        )

    def is_null(self, value: Any) -> bool:
        """Test for empty value."""
        if value is None:
            return True
        try:
            return len(value) == 0
        except TypeError:
            pass
        return False

    def extract_object(self, obj: Any, apply_filter=True) -> Dict:
        """Extract and filter attributes for a Gramps object."""
        data = {}
        for key, value in obj.__class__.__dict__.items():
            if isinstance(value, property):
                if key.startswith("_"):
                    key = key[2 + key.find("__") :]
                if apply_filter:
                    if self.filter_only_keys and key not in self.filter_only_keys:
                        continue
                    if self.filter_skip_keys and key in self.filter_skip_keys:
                        continue
                value = getattr(obj, key)
                if not self.strip_empty_keys or not self.is_null(value):
                    data[key] = value
        for key, value in obj.__dict__.items():
            if key.startswith("_"):
                key = key[2 + key.find("__") :]
            # Values we always filter out, data presented through different endpoint
            if key in ["thumb"]:
                continue
            if apply_filter:
                if self.filter_only_keys and key not in self.filter_only_keys:
                    continue
                if self.filter_skip_keys and key in self.filter_skip_keys:
                    continue
            if key == "rect" and value is None:
                value = []
            if key in ["mother_handle", "father_handle", "famc"] and value is None:
                value = ""
            if not self.strip_empty_keys or not self.is_null(value):
                data[key] = value
        return data

    def extract_objects(self, obj, level=0):
        """Recursively extract and filter object attributes."""
        if isinstance(obj, (str, int, bool)):
            return obj
        if isinstance(obj, lib.GrampsType):
            return obj.xml_str()
        if isinstance(
            obj,
            (
                BaseObject,
                lib.Date,
                lib.StyledText,
                lib.StyledTextTag,
                lib.Researcher,
                DbBookmarks,
            ),
        ):
            level = level + 1
            return self.extract_objects(
                self.extract_object(obj, bool(level == 1)), level=level
            )
        if isinstance(obj, type([])):
            result = []
            for item in obj:
                result.append(self.extract_objects(item, level=level))
            return result
        if isinstance(obj, type({})):
            result = {}
            for key in obj:
                if level == 0:
                    if self.filter_only_keys and key not in self.filter_only_keys:
                        continue
                    if self.filter_skip_keys and key in self.filter_skip_keys:
                        continue
                if not self.strip_empty_keys or not self.is_null(obj[key]):
                    result.update({key: self.extract_objects(obj[key], level=level)})
            return result
        return obj
