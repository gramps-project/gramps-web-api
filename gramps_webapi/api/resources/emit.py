"""Gramps Json Encoder"""

import inspect

import gramps.gen.lib as lib
from flask.json import JSONEncoder

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
        JSONEncoder.__init__(self)
        self.sort_keys = True
        self.ensure_ascii = False
        self.strip_empty_keys = False
        self.return_raw = False
        self.filter_keys = []

    def api_filter(self, obj):
        """Filter data in a Gramps object."""
        data = {}
        filter = False
        try:
            if isinstance(obj, PRIMARY_CLASS_MAP[self.gramps_class_name]):
                filter = True
        except:
            pass
        for key, value in obj.__dict__.items():
            if filter and self.filter_keys != [] and key not in self.filter_keys:
                continue
            if self.return_raw and key == "profile":
                continue
            if key.startswith("_"):
                key = key[2 + key.find("__") :]
            if self.strip_empty_keys:
                if isinstance(value, lib.GrampsType):
                    data[key] = str(value)
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

        for key, value in inspect.getmembers(lib, inspect.isclass):
            gramps_class = getattr(lib, key)
            if isinstance(obj, gramps_class):
                return self.api_filter(obj)

        return JSONEncoder.default(self, obj)
