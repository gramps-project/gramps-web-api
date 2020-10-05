"""Type API resource."""

from flask import Response, abort
from gramps.gen.db.base import DbReadBase

from ..util import get_dbstate
from . import ProtectedResource, Resource
from .emit import GrampsJSONEncoder


class TypeResource(ProtectedResource, GrampsJSONEncoder):
    """Type resource."""

    @property
    def db(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get(self, gramps_type: str):
        """Get the type."""
        db = self.db
        if gramps_type == "event_attribute":
            result = db.get_event_attribute_types()
        elif gramps_type == "event":
            result = db.get_event_types()
        elif gramps_type == "person_attribute":
            result = db.get_person_attribute_types()
        elif gramps_type == "family_attribute":
            result = db.get_event_types()
        elif gramps_type == "media_attribute":
            result = db.get_person_attribute_types()
        elif gramps_type == "family_relation":
            result = db.get_family_relation_types()
        elif gramps_type == "child_reference":
            result = db.get_child_reference_types()
        elif gramps_type == "event_roles":
            result = db.get_event_roles()
        elif gramps_type == "name":
            result = db.get_name_types()
        elif gramps_type == "origin":
            result = db.get_origin_types()
        elif gramps_type == "repository":
            result = db.get_repository_types()
        elif gramps_type == "note":
            result = db.get_note_types()
        elif gramps_type == "source_attribute":
            result = db.get_source_attribute_types()
        elif gramps_type == "source_media":
            result = db.get_source_media_types()
        elif gramps_type == "url":
            result = db.get_url_types()
        elif gramps_type == "place":
            result = db.get_place_types()

        return Response(
            response=self.encode(result),
            status=200,
            mimetype="application/json",
        )


class TypesResource(ProtectedResource, GrampsJSONEncoder):
    """Types resource."""

    def get(self):
        """Get the list of types."""
        result = [
            "event_attribute",
            "event",
            "person_attribute",
            "family_attribute",
            "media_attribute",
            "family_relation",
            "child_reference",
            "event_roles",
            "name",
            "origin",
            "repository",
            "note",
            "source_attribute",
            "source_media",
            "url",
            "place",
        ]

        return Response(
            response=self.encode(result),
            status=200,
            mimetype="application/json",
        )
