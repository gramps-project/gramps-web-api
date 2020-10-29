"""Metadata API resource."""

from typing import Dict

from flask import Response, abort
from gramps.gen.db.base import DbReadBase
from webargs import fields
from webargs.flaskparser import use_args

from ..util import get_dbstate
from . import ProtectedResource
from .emit import GrampsJSONEncoder


class MetadataResource(ProtectedResource, GrampsJSONEncoder):
    """Metadata resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    @use_args(
        {"type": fields.Str()},
        location="query",
    )
    def get(self, args: Dict, datatype: str) -> Response:
        """Get tree or application related metadata information."""
        db_handle = self.db_handle
        if datatype == "summary":
            summary = {}
            data = db_handle.get_summary()
            for item in data:
                summary[item.replace(" ", "_").lower()] = data[item]
            return self.response(200, summary)
        if datatype == "researcher":
            return self.response(200, db_handle.get_researcher())
        if datatype == "surnames":
            return self.response(200, db_handle.get_surname_list())
        if datatype == "types":
            if args.get("type"):
                if args["type"] == "event_attribute":
                    result = db_handle.get_event_attribute_types()
                elif args["type"] == "event":
                    result = db_handle.get_event_types()
                elif args["type"] == "person_attribute":
                    result = db_handle.get_person_attribute_types()
                elif args["type"] == "family_attribute":
                    result = db_handle.get_family_attribute_types()
                elif args["type"] == "media_attribute":
                    result = db_handle.get_media_attribute_types()
                elif args["type"] == "family_relation":
                    result = db_handle.get_family_relation_types()
                elif args["type"] == "child_reference":
                    result = db_handle.get_child_reference_types()
                elif args["type"] == "event_roles":
                    result = db_handle.get_event_roles()
                elif args["type"] == "name":
                    result = db_handle.get_name_types()
                elif args["type"] == "origin":
                    result = db_handle.get_origin_types()
                elif args["type"] == "repository":
                    result = db_handle.get_repository_types()
                elif args["type"] == "note":
                    result = db_handle.get_note_types()
                elif args["type"] == "source_attribute":
                    result = db_handle.get_source_attribute_types()
                elif args["type"] == "source_media":
                    result = db_handle.get_source_media_types()
                elif args["type"] == "url":
                    result = db_handle.get_url_types()
                elif args["type"] == "place":
                    result = db_handle.get_place_types()
                else:
                    abort(404)
            else:
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
            return self.response(200, result)
        abort(404)
