"""Base for Gramps object API resources."""

from abc import abstractmethod
from typing import Dict

from flask import Response, abort
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from webargs import fields
from webargs.flaskparser import use_args

from ..util import get_dbstate
from . import ProtectedResource, Resource
from .emit import GrampsJSONEncoder


class GrampsObjectResourceHelper(GrampsJSONEncoder):
    """Gramps object helper class."""

    @abstractmethod
    def object_extend(self, obj: GrampsObject, args: Dict) -> GrampsObject:
        """Extend the base object attributes as needed."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get_object_from_gramps_id(self, gramps_id: str) -> GrampsObject:
        """Get the object given a Gramps ID."""
        query_method = self.db_handle.method(
            "get_%s_from_gramps_id", self.gramps_class_name
        )
        return query_method(gramps_id)

    def get_object_from_handle(self, handle: str) -> GrampsObject:
        """Get the object given a Gramps handle."""
        query_method = self.db_handle.method(
            "get_%s_from_handle", self.gramps_class_name
        )
        return query_method(handle)


class GrampsObjectResource(GrampsObjectResourceHelper, Resource):
    """Resource for a single object."""

    @use_args(
        {
            "strip": fields.Boolean(missing=False),
            "keys": fields.DelimitedList(fields.Str()),
            "skipkeys": fields.DelimitedList(fields.Str(), missing=[]),
            "profile": fields.Boolean(missing=False),
            "extend": fields.Boolean(missing=False),
        },
        location="query",
    )
    def get(self, args: Dict, handle: str) -> Response:
        """Get the object."""
        try:
            obj = self.get_object_from_handle(handle)
        except HandleError:
            return abort(404)
        return self.response(self.object_extend(obj, args), args)


class GrampsObjectsResource(GrampsObjectResourceHelper, Resource):
    """Resource for multiple objects."""

    @use_args(
        {
            "gramps_id": fields.Str(),
            "handle": fields.Str(),
            "strip": fields.Boolean(missing=False),
            "keys": fields.DelimitedList(fields.Str()),
            "skipkeys": fields.DelimitedList(fields.Str(), missing=[]),
            "profile": fields.Boolean(missing=False),
            "extend": fields.Boolean(missing=False),
        },
        location="query",
    )
    def get(self, args: Dict) -> Response:
        """Get all objects."""
        if "gramps_id" in args:
            obj = self.get_object_from_gramps_id(args["gramps_id"])
            if obj is None:
                return abort(404)
            return self.response([self.object_extend(obj, args)], args)
        if "handle" in args:
            try:
                obj = self.get_object_from_handle(args["handle"])
            except HandleError:
                return abort(404)
            return self.response([self.object_extend(obj, args)], args)
        iter_method = self.db_handle.method("iter_%s_handles", self.gramps_class_name)
        query_method = self.db_handle.method(
            "get_%s_from_handle", self.gramps_class_name
        )
        return self.response(
            [
                self.object_extend(query_method(handle), args)
                for handle in iter_method()
            ],
            args,
        )


class GrampsObjectProtectedResource(GrampsObjectResource, ProtectedResource):
    """Resource for a single object, requiring authentication."""


class GrampsObjectsProtectedResource(GrampsObjectsResource, ProtectedResource):
    """Resource for a multiple objects, requiring authentication."""
