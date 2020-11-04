"""Base for Gramps object API resources."""

from abc import abstractmethod
from typing import Dict

from flask import Response, abort
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from webargs import fields, validate
from webargs.flaskparser import use_args

from ..util import get_dbstate
from . import ProtectedResource, Resource
from .emit import GrampsJSONEncoder
from .filters import apply_filter
from .util import get_backlinks, get_extended_attributes


class GrampsObjectResourceHelper(GrampsJSONEncoder):
    """Gramps object helper class."""

    @property  # type: ignore
    @abstractmethod
    def gramps_class_name(self):
        """To be set on child classes."""

    def full_object(self, obj: GrampsObject, args: Dict) -> GrampsObject:
        """Get the full object with extended attributes and backlinks."""
        obj = self.object_extend(obj, args)
        if args.get("backlinks"):
            obj.backlinks = get_backlinks(self.db_handle, obj.handle)
        return obj

    def object_extend(self, obj: GrampsObject, args: Dict) -> GrampsObject:
        """Extend the base object attributes as needed."""
        if "extend" in args:
            obj.extended = get_extended_attributes(self.db_handle, obj, args)
        return obj

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
            "strip": fields.Str(validate=validate.Length(equal=0)),
            "keys": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "skipkeys": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "profile": fields.Str(validate=validate.Length(equal=0)),
            "extend": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "formats": fields.DelimitedList(fields.Str()),
            "backlinks": fields.Boolean(missing=False),
        },
        location="query",
    )
    def get(self, args: Dict, handle: str) -> Response:
        """Get the object."""
        try:
            obj = self.get_object_from_handle(handle)
        except HandleError:
            abort(404)
        return self.response(200, self.full_object(obj, args), args)


class GrampsObjectsResource(GrampsObjectResourceHelper, Resource):
    """Resource for multiple objects."""

    @use_args(
        {
            "gramps_id": fields.Str(validate=validate.Length(min=1)),
            "strip": fields.Str(validate=validate.Length(equal=0)),
            "keys": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "skipkeys": fields.DelimitedList(
                fields.Str(validate=validate.Length(min=1))
            ),
            "profile": fields.Str(validate=validate.Length(equal=0)),
            "extend": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
            "filter": fields.Str(validate=validate.Length(min=1)),
            "rules": fields.Str(validate=validate.Length(min=1)),
            "formats": fields.DelimitedList(fields.Str()),
            "backlinks": fields.Boolean(missing=False),
        },
        location="query",
    )
    def get(self, args: Dict) -> Response:
        """Get all objects."""
        if "gramps_id" in args:
            obj = self.get_object_from_gramps_id(args["gramps_id"])
            if obj is None:
                abort(404)
            return self.response(200, [self.full_object(obj, args)], args)
        query_method = self.db_handle.method(
            "get_%s_from_handle", self.gramps_class_name
        )
        if "filter" in args or "rules" in args:
            handle_list = apply_filter(self.db_handle, args, self.gramps_class_name)
            return self.response(
                200,
                [
                    self.full_object(query_method(handle), args)
                    for handle in handle_list
                ],
                args,
            )
        iter_method = self.db_handle.method("iter_%s_handles", self.gramps_class_name)
        return self.response(
            200,
            [self.full_object(query_method(handle), args) for handle in iter_method()],
            args,
        )


class GrampsObjectProtectedResource(GrampsObjectResource, ProtectedResource):
    """Resource for a single object, requiring authentication."""


class GrampsObjectsProtectedResource(GrampsObjectsResource, ProtectedResource):
    """Resource for a multiple objects, requiring authentication."""
