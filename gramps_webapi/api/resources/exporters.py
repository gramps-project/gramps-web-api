#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2020      Christopher Horn
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Exporters Plugin API resource."""

import io
import os
import uuid
from mimetypes import types_map
from pathlib import Path
from typing import BinaryIO, Dict

from flask import Response, abort, current_app, send_file
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.const import TEMP_DIR

_ = glocale.translation.gettext
from gramps.gen.db.base import DbReadBase
from gramps.gen.filters import (
    CustomFilters,
    GenericFilter,
    reload_custom_filters,
    rules,
)
from gramps.gen.plug import BasePluginManager
from gramps.gen.proxy import (
    FilterProxyDb,
    LivingProxyDb,
    PrivateProxyDb,
    ReferencedBySelectionProxyDb,
)
from gramps.gen.user import User
from webargs import fields, validate
from webargs.flaskparser import use_args

from ..util import get_dbstate, get_locale_for_language
from . import ProtectedResource
from .emit import GrampsJSONEncoder
from .util import get_person_by_handle

LIVING_FILTERS = {
    "IncludeAll": LivingProxyDb.MODE_INCLUDE_ALL,
    "FullNameOnly": LivingProxyDb.MODE_INCLUDE_FULL_NAME_ONLY,
    "LastNameOnly": LivingProxyDb.MODE_INCLUDE_LAST_NAME_ONLY,
    "ReplaceCompleteName": LivingProxyDb.MODE_REPLACE_COMPLETE_NAME,
    "ExcludeAll": LivingProxyDb.MODE_EXCLUDE_ALL,
}


def get_exporters(extension: str = None):
    """Extract and return list of exporters."""
    exporters = []
    plugin_manager = BasePluginManager.get_instance()
    for plugin in plugin_manager.get_export_plugins():
        if extension is not None and extension != plugin.get_extension():
            continue
        exporter = {
            "description": plugin.get_description(),
            "extension": plugin.get_extension(),
            "module": plugin.get_module_name(),
        }
        exporters.append(exporter)
    return exporters


def prepare_options(db_handle: DbReadBase, args: Dict):
    """Prepare the export options."""
    options = ExportOptions()
    options.private = args["private"]
    options.living = LIVING_FILTERS[args["living"]]
    options.current_year = args["current_year"]
    options.years_after_death = args["years_after_death"]
    options.reference = args["reference"]
    options.include_individuals = int(args["include_individuals"])
    options.include_marriages = int(args["include_marriages"])
    options.include_children = int(args["include_children"])
    options.include_places = int(args["include_places"])
    options.translate_headers = int(args["translate_headers"])
    options.compression = int(args["compress"])
    if args["person"] is not None:
        gramps_id = args["gramps_id"]
        if gramps_id is None:
            if args["handle"] is not None:
                person = get_person_by_handle(db_handle, args["handle"])
                if not person:
                    abort(404)
                gramps_id = person.gramps_id
            else:
                abort(400)
        try:
            options.set_person_filter(args["person"], gramps_id)
        except ValueError:
            abort(404)
    if args["event"] is not None:
        try:
            options.set_event_filter(args["event"])
        except ValueError:
            abort(404)
    if args["note"] is not None:
        try:
            options.set_note_filter(args["note"])
        except ValueError:
            abort(404)
    try:
        options.set_proxy_order(args["sequence"])
    except ValueError:
        abort(422)
    if args["locale"] is not None:
        options.locale = get_locale_for_language(args["locale"])
        if options.locale is None:
            abort(404)
    return options


def run_export(
    db_handle: DbReadBase, extension: str, options, allow_file: bool = False
):
    """Generate the export."""
    export_path = TEMP_DIR
    if current_app.config.get("EXPORT_PATH"):
        export_path = current_app.config.get("EXPORT_PATH")
    file_name = os.path.join(export_path, "{}.{}".format(uuid.uuid4(), extension))
    plugin_manager = BasePluginManager.get_instance()
    for plugin in plugin_manager.get_export_plugins():
        if extension == plugin.get_extension():
            export_function = plugin.get_export_function()
            result = export_function(db_handle, file_name, User(), options)
            if not result:
                abort(500)
            return file_name, "." + extension


def fetch_buffer(filename: str, delete=True) -> BinaryIO:
    """Pull file into a binary buffer."""
    try:
        with open(filename, "rb") as file_handle:
            buffer = io.BytesIO(file_handle.read())
    except FileNotFoundError:
        abort(500)
    if delete:
        os.remove(filename)
    return buffer


class ExportersResource(ProtectedResource, GrampsJSONEncoder):
    """Exporters resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    @use_args({}, location="query")
    def get(self, args: Dict) -> Response:
        """Get all available exporter attributes."""
        db = self.db_handle
        return self.response(200, get_exporters())


class ExporterResource(ProtectedResource, GrampsJSONEncoder):
    """Export resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    @use_args({}, location="query")
    def get(self, args: Dict, exporter: str) -> Response:
        """Get specific report attributes."""
        db = self.db_handle
        exporters = get_exporters(exporter)
        if exporters == []:
            abort(404)
        return self.response(200, exporters[0])


class ExporterFileResource(ProtectedResource, GrampsJSONEncoder):
    """Export file resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    @use_args(
        {
            "compress": fields.Boolean(missing=True),
            "private": fields.Boolean(missing=False),
            "living": fields.Str(
                missing="IncludeAll",
                validate=validate.OneOf(
                    [
                        "IncludeAll",
                        "FullNameOnly",
                        "LastNameOnly",
                        "ReplaceCompleteName",
                        "ExcludeAll",
                    ]
                ),
            ),
            "current_year": fields.Integer(missing=None),
            "years_after_death": fields.Integer(missing=0),
            "locale": fields.Str(missing=None),
            "gramps_id": fields.Str(missing=None),
            "handle": fields.Str(missing=None),
            "person": fields.Str(missing=None),
            "event": fields.Str(missing=None),
            "note": fields.Str(missing=None),
            "reference": fields.Boolean(missing=False),
            "sequence": fields.Str(
                missing="privacy,living,person,event,note,reference"
            ),
            "include_individuals": fields.Boolean(missing=True),
            "include_marriages": fields.Boolean(missing=True),
            "include_children": fields.Boolean(missing=True),
            "include_places": fields.Boolean(missing=True),
            "translate_headers": fields.Boolean(missing=True),
        },
        location="query",
    )
    def get(self, args: Dict, exporter: str) -> Response:
        """Get export file."""
        db_handle = self.db_handle
        options = prepare_options(db_handle, args)
        file_name, file_type = run_export(db_handle, exporter, options)
        buffer = fetch_buffer(file_name)
        return send_file(buffer, mimetype=types_map[file_type])


# ExportOptions derived from WriterOptionBox, review of the database
# proxy classes and a review of exporter plugin code.


class ExportOptions:
    """Options for customizing various database exports."""

    def __init__(self):
        """Initialize class."""
        self.proxy_dbase = {}
        self.proxy_order = "privacy,living,person,event,note,reference"
        self.private = 0
        self.living = LivingProxyDb.MODE_INCLUDE_ALL
        self.current_year = None
        self.years_after_death = 0
        self.locale = glocale
        self.reference = 0
        self.gramps_id = None
        self.pfilter = None
        self.efilter = None
        self.nfilter = None
        self.compression = 1
        # Referenced by the csv export plugin
        self.include_individuals = 1
        self.include_marriages = 1
        self.include_children = 1
        self.include_places = 1
        self.translate_headers = 1

    def get_custom_filter(self, name: str, namespace: str):
        """Get the named custom filter from a namespace."""
        reload_custom_filters()
        for filter_class in CustomFilters.get_filters(namespace):
            if name == filter_class.get_name():
                return filter_class
        raise ValueError("can not find filter '%s' in namespace '%s'" % name, namespace)

    def set_person_filter(self, name: str, gramps_id: str):
        """Add the specified person filter."""
        self.gramps_id = gramps_id
        self.pfilter = GenericFilter()
        if name == "Descendants":
            self.pfilter.set_name(_("Descendants of %s") % name)
            self.pfilter.add_rule(rules.person.IsDescendantOf([gramps_id, 1]))
        elif name == "DescendantFamilies":
            self.pfilter.set_name(_("Descendant Families of %s") % name)
            self.pfilter.add_rule(rules.person.IsDescendantFamilyOf([gramps_id, 1]))
        elif name == "Ancestors":
            self.pfilter.set_name(_("Ancestors of %s") % name)
            self.pfilter.add_rule(rules.person.IsAncestorOf([gramps_id, 1]))
        elif name == "CommonAncestor":
            self.pfilter.set_name(_("People with common ancestor with %s") % name)
            self.pfilter.add_rule(rules.person.HasCommonAncestorWith([gramps_id]))
        else:
            self.pfilter = self.get_custom_filter(name, "people")

    def set_event_filter(self, name: str):
        """Add the specified event filter."""
        self.efilter = self.get_custom_filter(name, "events")

    def set_note_filter(self, name: str):
        """Add the specified note filter."""
        self.nfilter = self.get_custom_filter(name, "notes")

    # called by export plugins
    def get_use_compression(self):
        """Return compression mode."""
        return self.compression

    def set_proxy_order(self, sequence: str):
        """Set proxy order, used in place of ini."""
        for key in sequence.split(","):
            if key not in ["privacy", "living", "person", "event", "note", "reference"]:
                raise ValueError("invalid proxy order option '%s'" % key)
        self.proxy_order = sequence

    # called by export plugins
    def parse_options(self):
        """For compatibility with WriterOptionBox."""
        return

    # called by export plugins
    def get_filtered_database(self, dbase):
        """Apply filters to the database."""
        self.proxy_dbase.clear()
        for proxy_name in self.proxy_order.split(","):
            dbase = self.apply_proxy(proxy_name, dbase)
        return dbase

    def apply_proxy(self, proxy_name, dbase):
        """Apply the named proxy to the database and return."""
        if proxy_name == "privacy":
            if self.private:
                dbase = PrivateProxyDb(dbase)
        elif proxy_name == "living":
            if self.living != LivingProxyDb.MODE_INCLUDE_ALL:
                dbase = LivingProxyDb(dbase, self.living)
        elif proxy_name == "person":
            if self.pfilter is not None and not self.pfilter.is_empty():
                dbase = FilterProxyDb(dbase, person_filter=self.pfilter, user=User())
        elif proxy_name == "event":
            if self.efilter is not None and not self.efilter.is_empty():
                dbase = FilterProxyDb(dbase, event_filter=self.efilter, user=User())
        elif proxy_name == "note":
            if self.nfilter is not None and not self.nfilter.is_empty():
                dbase = FilterProxyDb(dbase, note_filter=self.nfilter, user=User())
        elif proxy_name == "reference":
            if self.reference:
                dbase = ReferencedBySelectionProxyDb(dbase, all_people=True)
        else:
            raise AttributeError("no such proxy '%s'" % proxy_name)
        return dbase
