"""Base for Gramps object API resources."""

from abc import abstractmethod

import gramps.gen.lib
from flask_restful import Resource, abort
from gramps.gen.db.dbconst import CLASS_TO_KEY_MAP, KEY_TO_NAME_MAP

from ..util import get_dbstate
from . import ProtectedResource


class GrampsObjectHelper:
    """Gramps object helper class."""

    @property  # type: ignore
    @abstractmethod
    def gramps_class_name(self):
        """To be set on child classes."""

    @staticmethod
    @abstractmethod
    def object_to_dict(obj):
        """Get the object as a dictionary."""

    @property
    def object_class(self):
        """Get the Gramps class of the object."""
        obj_class_name = KEY_TO_NAME_MAP[CLASS_TO_KEY_MAP[self.gramps_class_name]]
        obj_module = getattr(gramps.gen.lib, obj_class_name)
        obj_class = getattr(obj_module, self.gramps_class_name)
        return obj_class

    def get_object_from_gramps_id(self, gramps_id: str):
        """Get the object given a Gramps ID."""
        dbstate = get_dbstate()
        obj_class_key = CLASS_TO_KEY_MAP[self.gramps_class_name]
        raw_obj = dbstate.db._get_raw_from_id_data(obj_class_key, gramps_id)
        return self.object_class.create(raw_obj)


class GrampsObjectResource(GrampsObjectHelper, Resource):
    """Resource for a single object."""

    def get(self, gramps_id: str):
        """Get the object."""
        obj = self.get_object_from_gramps_id(gramps_id)
        if obj is None:
            return abort(404)
        return self.object_to_dict(obj)


class GrampsObjectsResource(GrampsObjectHelper, Resource):
    """Resource for multiple objects."""

    def get(self):
        """Get all objects."""
        dbstate = get_dbstate()
        return [
            self.object_to_dict(obj)
            for obj in dbstate.db._iter_objects(self.object_class)
        ]


class GrampsObjectProtectedResource(GrampsObjectResource, ProtectedResource):
    """Resource for a single object, requiring authentication."""


class GrampsObjectsProtectedResource(GrampsObjectsResource, ProtectedResource):
    """Resource for a multiple objects, requiring authentication."""
