"""Base for Gramps object API resources."""

from abc import abstractmethod

import gramps.gen.lib
from flask import abort
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from webargs import fields, validate
from webargs.flaskparser import use_args

from ..util import get_dbstate
from . import ProtectedResource, Resource
from .emit import GrampsJSONEncoder


class GrampsObjectResourceHelper(GrampsJSONEncoder):
    """Gramps object helper class."""

    def __init__(self):
        """Initialize class."""
        GrampsJSONEncoder.__init__(self)
        self.build_profile = False
        self.extend_object = False

    @property  # type: ignore
    @abstractmethod
    def gramps_class_name(self):
        """To be set on child classes."""

    @abstractmethod
    def object_extend(self, obj):
        """Extend the base object attributes as needed."""

    @abstractmethod
    def object_filter(self, args):
        """Apply a filter against objects of the current type."""

    @abstractmethod
    def object_filter_rules(self):
        """Get list of filter rules for current object type."""

    @property
    def db(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get_object_from_gramps_id(self, gramps_id: str):
        """Get the object given a Gramps ID."""
        query_method = self.db.method("get_%s_from_gramps_id", self.gramps_class_name)
        return query_method(gramps_id)

    def get_object_from_handle(self, handle: str):
        """Get the object given a Gramps handle."""
        query_method = self.db.method("get_%s_from_handle", self.gramps_class_name)
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
    def get(self, args, handle: str):
        """Get the object."""
        try:
            obj = self.get_object_from_handle(handle)
        except HandleError:
            return abort(404)
        self.strip_empty_keys = args["strip"]
        if "keys" in args:
            self.filter_only_keys = args["keys"]
        self.filter_skip_keys = args["skipkeys"]
        self.build_profile = args["profile"]
        self.extend_object = args["extend"]
        return self.response(self.object_extend(obj))


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
            "rules": fields.Boolean(),
            "logic": fields.Str(
                missing="and", validate=validate.OneOf(["and", "or", "xor", "one"])
            ),
            "invert": fields.Boolean(missing=False),
            "filter": fields.Raw(),
        },
        location="query",
    )
    def get(self, args):
        """Get all objects."""
        self.strip_empty_keys = args["strip"]
        if "keys" in args:
            self.filter_only_keys = args["keys"]
        self.filter_skip_keys = args["skipkeys"]
        self.build_profile = args["profile"]
        self.extend_object = args["extend"]
        if "rules" in args:
            return self.response(self.object_filter_rules())
        if "gramps_id" in args:
            obj = self.get_object_from_gramps_id(args["gramps_id"])
            if obj is None:
                return abort(404)
            return self.response([self.object_extend(obj)])
        if "handle" in args:
            try:
                obj = self.get_object_from_handle(handle)
            except HandleError:
                return abort(404)
            return self.response([self.object_extend(obj)])
        query_method = self.db.method("get_%s_from_handle", self.gramps_class_name)
        if "filter" in args:
            handle_list = self.object_filter(args)
            return self.response(
                [self.object_extend(query_method(handle)) for handle in handle_list]
            )
        iter_method = self.db.method("iter_%s_handles", self.gramps_class_name)
        return self.response(
            [self.object_extend(query_method(handle)) for handle in iter_method()]
        )


class GrampsObjectProtectedResource(GrampsObjectResource, ProtectedResource):
    """Resource for a single object, requiring authentication."""


class GrampsObjectsProtectedResource(GrampsObjectsResource, ProtectedResource):
    """Resource for a multiple objects, requiring authentication."""
