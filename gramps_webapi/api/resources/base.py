"""Base for Gramps object API resources."""

from abc import abstractmethod

import gramps.gen.lib
from flask import abort
from gramps.gen.db.base import DbReadBase
from gramps.gen.db.dbconst import CLASS_TO_KEY_MAP, KEY_TO_NAME_MAP
from gramps.gen.errors import HandleError
from webargs import fields
from webargs.flaskparser import use_args

from ..util import get_dbstate
from . import ProtectedResource, Resource
from .emit import GrampsJSONEncoder


class GrampsObjectResourceHelper(GrampsJSONEncoder):
    """Gramps object helper class."""

    @property  # type: ignore
    @abstractmethod
    def gramps_class_name(self):
        """To be set on child classes."""

    @abstractmethod
    def object_denormalize(self, obj):
        """Denormalize object attributes as needed."""

    @property
    def db(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    @property
    def object_class(self):
        """Get the Gramps class of the object."""
        obj_class_name = KEY_TO_NAME_MAP[CLASS_TO_KEY_MAP[self.gramps_class_name]]
        if obj_class_name == "source":
            obj_class_name = "src"
        elif obj_class_name == "repository":
            obj_class_name = "repo"
        obj_module = getattr(gramps.gen.lib, obj_class_name)
        obj_class = getattr(obj_module, self.gramps_class_name)
        return obj_class

    def get_object_from_gramps_id(self, gramps_id: str):
        """Get the object given a Gramps ID."""
        obj_class_key = CLASS_TO_KEY_MAP[self.gramps_class_name]
        raw_obj = self.db._get_raw_from_id_data(obj_class_key, gramps_id)
        return self.object_class.create(raw_obj)

    def get_object_from_handle(self, handle: str):
        """Get the object given a Gramps handle."""
        obj_class_key = CLASS_TO_KEY_MAP[self.gramps_class_name]
        return self.db._get_from_handle(obj_class_key, self.object_class, handle)

    def get_gramps_id_from_handle(self, handle: str):
        """Get an object's Gramps ID from its handle."""
        return self.get_object_from_handle(handle).gramps_id


class GrampsObjectResource(GrampsObjectResourceHelper, Resource):
    """Resource for a single object."""

    @use_args(
        {
            "strip": fields.Boolean(),
            "raw": fields.Boolean(),
            "keys": fields.DelimitedList(fields.Str()),
        },
        location="query",
    )
    def get(self, args, handle: str):
        """Get the object."""
        try:
            obj = self.get_object_from_handle(handle)
        except HandleError:
            return abort(404)
        if "strip" in args:
            self.strip_empty_keys = args["strip"]
        if "raw" in args:
            self.return_raw = args["raw"]
        if "keys" in args:
            self.filter_keys = args["keys"]
        return self.response(self.object_denormalize(obj))


class GrampsObjectsResource(GrampsObjectResourceHelper, Resource):
    """Resource for multiple objects."""

    @use_args(
        {
            "gramps_id": fields.Str(),
            "handle": fields.Str(),
            "strip": fields.Boolean(),
            "raw": fields.Boolean(),
            "keys": fields.DelimitedList(fields.Str()),
        },
        location="query",
    )
    def get(self, args):
        """Get all objects."""
        if "strip" in args:
            self.strip_empty_keys = args["strip"]
        if "raw" in args:
            self.return_raw = args["raw"]
        if "keys" in args:
            self.filter_keys = args["keys"]
        if "gramps_id" in args:
            obj = self.get_object_from_gramps_id(args["gramps_id"])
            if obj is None:
                return abort(404)
            return self.response([self.object_denormalize(obj)])
        if "handle" in args:
            try:
                obj = self.get_object_from_handle(handle)
            except HandleError:
                return abort(404)
            return self.response([self.object_denormalize(obj)])
        return self.response(
            [
                self.object_denormalize(obj)
                for obj in self.db._iter_objects(self.object_class)
            ]
        )


class GrampsObjectProtectedResource(GrampsObjectResource, ProtectedResource):
    """Resource for a single object, requiring authentication."""


class GrampsObjectsProtectedResource(GrampsObjectsResource, ProtectedResource):
    """Resource for a multiple objects, requiring authentication."""
