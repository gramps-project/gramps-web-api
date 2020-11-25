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

import inspect
from typing import Any, Dict, Optional

import gramps.gen.lib as lib
from flask import Response
from flask.json import JSONEncoder
from gramps.gen.db import DbBookmarks

from ...const import PRIMARY_GRAMPS_OBJECTS


class GrampsJSONEncoder(JSONEncoder):
    """Customizes Gramps Web API output."""

    gramps_class_name = ""

    def __init__(self):
        """Initialize class."""
        JSONEncoder.__init__(self, ensure_ascii=False, sort_keys=True)
        self.strip_empty_keys = False
        self.filter_only_keys = []
        self.filter_skip_keys = []
        self.gramps_classes = [
            getattr(lib, key) for key, value in inspect.getmembers(lib, inspect.isclass)
        ]

    def response(
        self,
        status: int = 200,
        payload: Optional[Any] = None,
        args: Optional[Dict] = None,
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

        return Response(
            response=self.encode(payload),
            status=status,
            mimetype="application/json",
        )

    def api_filter(self, obj: Any) -> Dict:
        """Filter data for a Gramps object."""

        def is_null(value: Any) -> bool:
            """Test for empty value."""
            if value is None:
                return True
            try:
                return len(value) == 0
            except TypeError:
                pass
            return False

        data = {}
        apply_filter = False
        if (
            hasattr(self, "gramps_class_name")
            and self.gramps_class_name
            and isinstance(obj, PRIMARY_GRAMPS_OBJECTS[self.gramps_class_name])
        ):
            apply_filter = True
        for key, value in obj.__class__.__dict__.items():
            if key.startswith("_"):
                key = key[2 + key.find("__") :]
            if apply_filter:
                if self.filter_only_keys and key not in self.filter_only_keys:
                    continue
                if self.filter_skip_keys and key in self.filter_skip_keys:
                    continue
            if isinstance(value, property):
                value = getattr(obj, key)
                if not self.strip_empty_keys or not is_null(value):
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
            # Values we normalize for schema consistency
            if key == "rect" and value is None:
                value = []
            if key in ["mother_handle", "father_handle", "famc"] and value is None:
                value = ""
            if not self.strip_empty_keys or not is_null(value):
                data[key] = value
        return data

    def default(self, obj: Any):
        """Our default handler."""
        if isinstance(obj, lib.GrampsType):
            return obj.xml_str()

        for gramps_class in self.gramps_classes:
            if isinstance(obj, gramps_class):
                return self.api_filter(obj)

        if isinstance(obj, DbBookmarks):
            return self.api_filter(obj)

        return JSONEncoder.default(self, obj)
