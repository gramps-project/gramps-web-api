"""Types API resource."""

from typing import Dict

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
from gramps.gen.relationship import RelationshipCalculator
from webargs import fields
from webargs.flaskparser import use_args

from ..util import get_dbstate
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

calc = RelationshipCalculator()

_SIBLING_TYPES = {
    calc.NORM_SIB: "Sibling",
    calc.HALF_SIB_MOTHER: "Maternal Half Sibling",
    calc.HALF_SIB_FATHER: "Paternal Half Sibling",
    calc.STEP_SIB: "Step Sibling",
    calc.UNKNOWN_SIB: "Unknown Sibling",
}

_PARTNER_TYPES = {
    calc.PARTNER_MARRIED: "Married",
    calc.PARTNER_UNMARRIED: "Unmarried",
    calc.PARTNER_CIVIL_UNION: "Civil Union",
    calc.PARTNER_UNKNOWN_REL: "Unknown Relationship",
    calc.PARTNER_EX_MARRIED: "Ex-Married",
    calc.PARTNER_EX_UNMARRIED: "Ex-Unmarried",
    calc.PARTNER_EX_CIVIL_UNION: "Ex-Civil Union",
    calc.PARTNER_EX_UNKNOWN_REL: "Ex-Unknown Relationship",
}


class DefaultTypesResource(ProtectedResource, GrampsJSONEncoder):
    """Default types resource."""

    def get(self) -> Response:
        """Return a list of available default types."""
        result = [
            "attribute_types",
            "child_reference_types",
            "event_role_types",
            "event_types",
            "family_relation_types",
            "gender_types",
            "name_origin_types",
            "name_types",
            "note_types",
            "partner_types",
            "place_types",
            "repository_types",
            "sibling_types",
            "source_attribute_types",
            "source_media_types",
            "url_types",
        ]
        return self.response(200, result)


class DefaultTypeResource(ProtectedResource, GrampsJSONEncoder):
    """Default type resource."""

    @use_args(
        {
            "locale": fields.Boolean(missing=False),
        },
        location="query",
    )
    def get(self, args: Dict, datatype: str) -> Response:
        """Return a list of values for a default type."""
        if datatype in _DEFAULT_TYPE_CLASSES:
            types = _DEFAULT_TYPE_CLASSES[datatype]
            if args["locale"]:
                result = types.get_standard_names()
            else:
                result = types.get_standard_xml()
        elif datatype == "sibling_types":
            result = [_SIBLING_TYPES[x] for x in _SIBLING_TYPES]
        elif datatype == "partner_types":
            result = [_PARTNER_TYPES[x] for x in _PARTNER_TYPES]
        elif datatype == "gender_types":
            result = [_GENDER_TYPES[x] for x in _GENDER_TYPES]
        else:
            abort(404)
        return self.response(200, result)


class DefaultTypeMapResource(ProtectedResource, GrampsJSONEncoder):
    """Default type resource."""

    def get(self, datatype: str) -> Response:
        """Return the map for a default type."""
        if datatype in _DEFAULT_TYPE_CLASSES:
            types = _DEFAULT_TYPE_CLASSES[datatype]
            result = types.get_map()
        elif datatype == "sibling_types":
            result = _SIBLING_TYPES
        elif datatype == "partner_types":
            result = _PARTNER_TYPES
        elif datatype == "gender_types":
            result = _GENDER_TYPES
        else:
            abort(404)
        return self.response(200, result)


class CustomTypesResource(ProtectedResource, GrampsJSONEncoder):
    """Custom types resource."""

    def get(self) -> Response:
        """Return a list of available custom types."""
        result = [
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
        return self.response(200, result)


class CustomTypeResource(ProtectedResource, GrampsJSONEncoder):
    """Custom type resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get(self, datatype: str) -> Response:
        """Return list of values for the custom type."""
        db_handle = self.db_handle
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
        else:
            abort(404)
        return self.response(200, result)
