"""Type API resource."""

from flask import Response, abort
from gramps.gen.db.base import DbReadBase

from gramps_webapi.api.util import get_dbstate

from . import ProtectedResource
from .emit import GrampsJSONEncoder


class TypeResource(ProtectedResource, GrampsJSONEncoder):
    """Type resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get(self, gramps_type: str) -> Response:
        """Get the type."""
        db_handle = self.db_handle
        if gramps_type == "event_attribute":
            result = db_handle.get_event_attribute_types()
        elif gramps_type == "event":
            result = db_handle.get_event_types()
        elif gramps_type == "person_attribute":
            result = db_handle.get_person_attribute_types()
        elif gramps_type == "family_attribute":
            result = db_handle.get_family_attribute_types()
        elif gramps_type == "media_attribute":
            result = db_handle.get_person_attribute_types()
        elif gramps_type == "family_relation":
            result = db_handle.get_family_relation_types()
        elif gramps_type == "child_reference":
            result = db_handle.get_child_reference_types()
        elif gramps_type == "event_roles":
            result = db_handle.get_event_roles()
        elif gramps_type == "name":
            result = db_handle.get_name_types()
        elif gramps_type == "origin":
            result = db_handle.get_origin_types()
        elif gramps_type == "repository":
            result = db_handle.get_repository_types()
        elif gramps_type == "note":
            result = db_handle.get_note_types()
        elif gramps_type == "source_attribute":
            result = db_handle.get_source_attribute_types()
        elif gramps_type == "source_media":
            result = db_handle.get_source_media_types()
        elif gramps_type == "url":
            result = db_handle.get_url_types()
        elif gramps_type == "place":
            result = db_handle.get_place_types()
        else:
            return abort(404)
        return self.response(result)


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
