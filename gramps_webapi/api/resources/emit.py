"""Gramps Json Encoder."""

import inspect

import gramps.gen.lib as lib
from flask import Response
from flask.json import JSONEncoder
from gramps.gen.db import DbBookmarks

PRIMARY_CLASS_MAP = {
    "Person": lib.Person,
    "Family": lib.Family,
    "Event": lib.Event,
    "Place": lib.Place,
    "Source": lib.Source,
    "Citation": lib.Citation,
    "Repository": lib.Repository,
    "Media": lib.Media,
    "Note": lib.Note,
    "Tag": lib.Tag,
}


class GrampsJSONEncoder(JSONEncoder):
    """Customizes Gramps Web API output."""

    def __init__(self):
        """Initialize class."""
        JSONEncoder.__init__(self)
        self.sort_keys = True
        self.ensure_ascii = False
        self.strip_empty_keys = False
        self.filter_only_keys = []
        self.filter_skip_keys = []
        self.gramps_classes = [
            getattr(lib, key) for key, value in inspect.getmembers(lib, inspect.isclass)
        ]

    def response(self, payload):
        """Prepare response."""
        return Response(
            response=self.encode(payload),
            status=200,
            mimetype="application/json",
        )

    def api_filter(self, obj):
        """Filter data for a Gramps object."""
        data = {}
        filter = False
        try:
            if isinstance(obj, PRIMARY_CLASS_MAP[self.gramps_class_name]):
                filter = True
        except:
            pass
        for key, value in obj.__dict__.items():
            if filter:
                if self.filter_only_keys != [] and key not in self.filter_only_keys:
                    continue
                if self.filter_skip_keys != [] and key in self.filter_skip_keys:
                    continue
            if key.startswith("_"):
                key = key[2 + key.find("__") :]
            if self.strip_empty_keys:
                if isinstance(value, lib.GrampsType):
                    data[key] = str(value)
                elif isinstance(value, lib.StyledText):
                    data[key] = str(value)
                elif isinstance(value, lib.PlaceName):
                    data[key] = {
                        "date": value.date,
                        "lang": value.lang,
                        "value": value.value,
                    }
                else:
                    if value is not None and value != [] and value != {}:
                        data[key] = value
            else:
                data[key] = value
        return data

    def default(self, obj):
        """Default handler."""
        if isinstance(obj, lib.GrampsType):
            return str(obj)

        for gramps_class in self.gramps_classes:
            if isinstance(obj, gramps_class):
                return self.api_filter(obj)

        if isinstance(obj, DbBookmarks):
            return self.api_filter(obj)

        return JSONEncoder.default(self, obj)
