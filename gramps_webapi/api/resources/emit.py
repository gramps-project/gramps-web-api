"""Gramps Json Encoder."""

import inspect
from typing import Any, Dict

import gramps.gen.lib as lib
from flask import Response
from flask.json import JSONEncoder
from gramps.gen.db import DbBookmarks


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

    def response(self, payload: Any, args: Dict = {}) -> Response:
        """Prepare response."""
        if "strip" in args:
            self.strip_empty_keys = args["strip"]
        if "keys" in args:
            self.filter_only_keys = args["keys"]
        if "skipkeys" in args:
            self.filter_skip_keys = args["skipkeys"]

        return Response(
            response=self.encode(payload),
            status=200,
            mimetype="application/json",
        )

    def api_filter(self, obj: Any) -> Dict:
        """Filter data for a Gramps object."""
        data = {}
        apply_filter = bool(self.gramps_class_name)
        for key, value in obj.__dict__.items():
            if apply_filter:
                if self.filter_only_keys and key not in self.filter_only_keys:
                    continue
                if self.filter_skip_keys and key in self.filter_skip_keys:
                    continue
            if key.startswith("_"):
                key = key[2 + key.find("__") :]
            if not self.strip_empty_keys or value:
                data[key] = value
        return data

    def default(self, obj: Any):
        """Our default handler."""
        if isinstance(obj, lib.GrampsType):
            return str(obj)

        for gramps_class in self.gramps_classes:
            if isinstance(obj, gramps_class):
                return self.api_filter(obj)

        if isinstance(obj, DbBookmarks):
            return self.api_filter(obj)

        return JSONEncoder.default(self, obj)