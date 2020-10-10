"""Type API resource."""

from flask import Response, abort
from gramps.gen.db.base import DbReadBase
from gramps_webapi.api.util import get_dbstate

from . import ProtectedResource, Resource
from .emit import GrampsJSONEncoder


class TypeResource(ProtectedResource, GrampsJSONEncoder):
    """Type resource."""

    @property
    def db(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get(self, gramps_type: str) -> Response:
        """Get the type."""
        db = self.db
        if gramps_type == "event_attribute":
            return self.response(db.get_event_attribute_types())
        if gramps_type == "event":
            return self.response(db.get_event_types())
        if gramps_type == "person_attribute":
            return self.response(db.get_person_attribute_types())
        if gramps_type == "family_attribute":
            return self.response(db.get_family_attribute_types())
        if gramps_type == "media_attribute":
            return self.response(db.get_person_attribute_types())
        if gramps_type == "family_relation":
            return self.response(db.get_family_relation_types())
        if gramps_type == "child_reference":
            return self.response(db.get_child_reference_types())
        if gramps_type == "event_roles":
            return self.response(db.get_event_roles())
        if gramps_type == "name":
            return self.response(db.get_name_types())
        if gramps_type == "origin":
            return self.response(db.get_origin_types())
        if gramps_type == "repository":
            return self.response(db.get_repository_types())
        if gramps_type == "note":
            return self.response(db.get_note_types())
        if gramps_type == "source_attribute":
            return self.response(db.get_source_attribute_types())
        if gramps_type == "source_media":
            return self.response(db.get_source_media_types())
        if gramps_type == "url":
            return self.response(db.get_url_types())
        if gramps_type == "place":
            return self.response(db.get_place_types())
        return abort(404)


class TypesResource(ProtectedResource, GrampsJSONEncoder):
    """Types resource."""

    def get(self) -> Response:
        """Get the list of types."""
        return self.response(
            [
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
        )
