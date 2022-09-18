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

"""Types API resource."""

from typing import Dict, List, Optional

from flask import Response, abort
from gramps.gen.db.base import DbReadBase
from gramps.gen.lib.attrtype import AttributeType
from gramps.gen.lib.childreftype import ChildRefType
from gramps.gen.lib.eventroletype import EventRoleType
from gramps.gen.lib.eventtype import EventType
from gramps.gen.lib.familyreltype import FamilyRelType
from gramps.gen.lib.nameorigintype import NameOriginType
from gramps.gen.lib.nametype import NameType
from gramps.gen.lib.notetype import NoteType
from gramps.gen.lib.person import Person
from gramps.gen.lib.placetype import PlaceType
from gramps.gen.lib.repotype import RepositoryType
from gramps.gen.lib.srcattrtype import SrcAttributeType
from gramps.gen.lib.srcmediatype import SourceMediaType
from gramps.gen.lib.urltype import UrlType
from webargs import fields

from ..util import use_args
from ..util import get_db_handle
from . import ProtectedResource
from .emit import GrampsJSONEncoder

_DEFAULT_TYPE_CLASSES = {
    "attribute_types": AttributeType(),
    "event_types": EventType(),
    "event_role_types": EventRoleType(),
    "child_reference_types": ChildRefType(),
    "family_relation_types": FamilyRelType(),
    "name_origin_types": NameOriginType(),
    "name_types": NameType(),
    "note_types": NoteType(),
    "place_types": PlaceType(),
    "repository_types": RepositoryType(),
    "source_attribute_types": SrcAttributeType(),
    "source_media_types": SourceMediaType(),
    "url_types": UrlType(),
}

person = Person()

_GENDER_TYPES = {
    person.MALE: "Male",
    person.FEMALE: "Female",
    person.UNKNOWN: "Unknown",
}

_DEFAULT_RECORD_TYPES = [
    "attribute_types",
    "child_reference_types",
    "event_role_types",
    "event_types",
    "family_relation_types",
    "gender_types",
    "name_origin_types",
    "name_types",
    "note_types",
    "place_types",
    "repository_types",
    "source_attribute_types",
    "source_media_types",
    "url_types",
]

_CUSTOM_RECORD_TYPES = [
    "child_reference_types",
    "event_attribute_types",
    "event_role_types",
    "event_types",
    "family_attribute_types",
    "family_relation_types",
    "media_attribute_types",
    "name_origin_types",
    "name_types",
    "note_types",
    "person_attribute_types",
    "place_types",
    "repository_types",
    "source_attribute_types",
    "source_media_types",
    "url_types",
]


def get_default_types(datatype: str, locale: bool = False) -> Optional[List]:
    """Return list of types for a default record type."""
    result = None
    if datatype in _DEFAULT_TYPE_CLASSES:
        types = _DEFAULT_TYPE_CLASSES[datatype]
        if locale:
            result = types.get_standard_names()
        else:
            result = types.get_standard_xml()
    elif datatype == "gender_types":
        result = [_GENDER_TYPES[x] for x in _GENDER_TYPES]
    return result


def get_custom_types(db_handle: DbReadBase, datatype: str) -> Optional[List]:
    """Return list of types for a custom record type."""
    result = None
    if datatype == "event_attribute_types":
        result = db_handle.get_event_attribute_types()
    elif datatype == "event_types":
        result = db_handle.get_event_types()
    elif datatype == "person_attribute_types":
        result = db_handle.get_person_attribute_types()
    elif datatype == "family_attribute_types":
        result = db_handle.get_family_attribute_types()
    elif datatype == "media_attribute_types":
        result = db_handle.get_media_attribute_types()
    elif datatype == "family_relation_types":
        result = db_handle.get_family_relation_types()
    elif datatype == "child_reference_types":
        result = db_handle.get_child_reference_types()
    elif datatype == "event_role_types":
        result = db_handle.get_event_roles()
    elif datatype == "name_types":
        result = db_handle.get_name_types()
    elif datatype == "name_origin_types":
        result = db_handle.get_origin_types()
    elif datatype == "repository_types":
        result = db_handle.get_repository_types()
    elif datatype == "note_types":
        result = db_handle.get_note_types()
    elif datatype == "source_attribute_types":
        result = db_handle.get_source_attribute_types()
    elif datatype == "source_media_types":
        result = db_handle.get_source_media_types()
    elif datatype == "url_types":
        result = db_handle.get_url_types()
    elif datatype == "place_types":
        result = db_handle.get_place_types()
    return result


class DefaultTypesResource(ProtectedResource, GrampsJSONEncoder):
    """Default types resource."""

    @use_args(
        {
            "locale": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def get(self, args: Dict) -> Response:
        """Return a list of available default types."""
        result = {}
        for datatype in _DEFAULT_RECORD_TYPES:
            result.update({datatype: get_default_types(datatype, args["locale"])})
        return self.response(200, result)


class DefaultTypeResource(ProtectedResource, GrampsJSONEncoder):
    """Default type resource."""

    @use_args(
        {
            "locale": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def get(self, args: Dict, datatype: str) -> Response:
        """Return a list of values for a default type."""
        result = get_default_types(datatype, args["locale"])
        if result is None:
            abort(404)
        return self.response(200, result)


class DefaultTypeMapResource(ProtectedResource, GrampsJSONEncoder):
    """Default type resource."""

    @use_args(
        {},
        location="query",
    )
    def get(self, args: Dict, datatype: str) -> Response:
        """Return the map for a default type."""
        if datatype in _DEFAULT_TYPE_CLASSES:
            types = _DEFAULT_TYPE_CLASSES[datatype]
            result = types.get_map()
        elif datatype == "gender_types":
            result = _GENDER_TYPES
        else:
            abort(404)
        return self.response(200, result)


class CustomTypesResource(ProtectedResource, GrampsJSONEncoder):
    """Custom types resource."""

    @use_args(
        {},
        location="query",
    )
    def get(self, args: Dict) -> Response:
        """Return a list of available custom types."""
        result = {}
        for datatype in _CUSTOM_RECORD_TYPES:
            result.update({datatype: get_custom_types(get_db_handle(), datatype)})
        return self.response(200, result)


class CustomTypeResource(ProtectedResource, GrampsJSONEncoder):
    """Custom type resource."""

    @use_args(
        {},
        location="query",
    )
    def get(self, args: Dict, datatype: str) -> Response:
        """Return list of values for the custom type."""
        result = get_custom_types(get_db_handle(), datatype)
        if result is None:
            abort(404)
        return self.response(200, result)


class TypesResource(ProtectedResource, GrampsJSONEncoder):
    """Types resource."""

    @use_args(
        {
            "locale": fields.Boolean(load_default=False),
        },
        location="query",
    )
    def get(self, args: Dict) -> Response:
        """Return list of values for the custom type."""
        custom = {}
        for datatype in _CUSTOM_RECORD_TYPES:
            custom.update({datatype: get_custom_types(get_db_handle(), datatype)})
        default = {}
        for datatype in _DEFAULT_RECORD_TYPES:
            default.update({datatype: get_default_types(datatype, args["locale"])})
        return self.response(200, {"default": default, "custom": custom})
