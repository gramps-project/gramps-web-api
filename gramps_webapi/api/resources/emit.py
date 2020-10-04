"""Gramps Json Encoder"""

from flask.json import JSONEncoder
import gramps.gen.lib as lib


class GrampsJSONEncoder(JSONEncoder):

    def __init__(self):
        JSONEncoder.__init__(self)
        self.sort_keys = True
        self.ensure_ascii = False
        self.strip_empty_keys = False
        self.return_raw = False
        self.filter_keys = []

    def api_filter(self, obj):
        data = {}
        for key, value in obj.__dict__.items():
            if self.filter_keys != [] and key not in self.filter_keys:
                continue
            if self.return_raw and key == 'profile':
                continue
            if key.startswith('_'):
                key = key[2+key.find('__'):]
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
        if isinstance(obj, lib.GrampsType):
            return str(obj)

        for gramps_type in [lib.Place, lib.PlaceName, lib.Date, lib.Note, lib.Citation,
                            lib.Person, lib.Family, lib.ChildRef, lib.Event, lib.EventRef,
                            lib.Attribute, lib.Name, lib.Surname, lib.Media, lib.MediaRef,
                            lib.Source, lib.Repository, lib.Tag, lib.RepoRef, lib.PersonRef,
                            lib.Address, lib.StyledText, lib.StyledTextTag]:
            if isinstance(obj, gramps_type):
                return self.api_filter(obj)

        return JSONEncoder.default(self, obj)
