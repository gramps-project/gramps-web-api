#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2007-2008 Donald N. Allingham
# Copyright (C) 2008      Gary Burton
# Copyright (C) 2008      Robert Cheramy <robert@cheramy.net>
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

import mimetypes
import os
import tempfile
import uuid
from pathlib import Path
from typing import Dict

from flask import Response, abort, current_app, send_file
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.errors import HandleError

_ = glocale.translation.gettext
import gramps.gen.filters as filters
from gramps.gen.db.base import DbReadBase
from gramps.gen.plug import BasePluginManager
from gramps.gen.proxy import (
    FilterProxyDb,
    LivingProxyDb,
    PrivateProxyDb,
    ReferencedBySelectionProxyDb,
)
from gramps.gen.user import User
from gramps.gen.utils.resourcepath import ResourcePath
from webargs import fields, validate

from ..util import get_buffer_for_file, get_db_handle, get_locale_for_language, use_args
from . import ProtectedResource
from .emit import GrampsJSONEncoder

LIVING_FILTERS = {
    "IncludeAll": LivingProxyDb.MODE_INCLUDE_ALL,
    "FullNameOnly": LivingProxyDb.MODE_INCLUDE_FULL_NAME_ONLY,
    "LastNameOnly": LivingProxyDb.MODE_INCLUDE_LAST_NAME_ONLY,
    "ReplaceCompleteName": LivingProxyDb.MODE_REPLACE_COMPLETE_NAME,
    "ExcludeAll": LivingProxyDb.MODE_EXCLUDE_ALL,
}

mimetypes.init()


def get_exporters(extension: str = None):
    """Extract and return list of exporters."""
    exporters = []
    plugin_manager = BasePluginManager.get_instance()
    for plugin in plugin_manager.get_export_plugins():
        if extension is not None and extension != plugin.get_extension():
            continue
        exporter = {
            "name": plugin.get_name(),
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
    options.include_witnesses = int(args["include_witnesses"])
    options.include_media = int(args["include_media"])
    options.translate_headers = int(args["translate_headers"])
    options.compression = int(args["compress"])
    if args["person"] is None:
        if args["gramps_id"] is not None or args["handle"] is not None:
            abort(422)
    else:
        if args["gramps_id"] is not None:
            gramps_id = args["gramps_id"]
            if db_handle.get_person_from_gramps_id(gramps_id) is None:
                abort(422)
        else:
            try:
                person = db_handle.get_person_from_handle(args["handle"])
            except HandleError:
                abort(422)
            gramps_id = person.gramps_id
        try:
            options.set_person_filter(args["person"], gramps_id)
        except ValueError:
            abort(422)
    if args["event"] is not None:
        try:
            options.set_event_filter(args["event"])
        except ValueError:
            abort(422)
    if args["note"] is not None:
        try:
            options.set_note_filter(args["note"])
        except ValueError:
            abort(422)
    try:
        options.set_proxy_order(args["sequence"])
    except ValueError:
        abort(422)
    if args["locale"] is not None:
        options.locale = get_locale_for_language(args["locale"])
        if options.locale is None:
            abort(422)
    return options


def run_export(db_handle: DbReadBase, extension: str, options):
    """Generate the export."""
    if current_app.config.get("EXPORT_DIR"):
        export_path = current_app.config.get("EXPORT_DIR")
    else:
        export_path = tempfile.gettempdir()
    file_name = os.path.join(export_path, "{}.{}".format(uuid.uuid4(), extension))
    _resources = ResourcePath()
    os.environ["GRAMPS_RESOURCES"] = str(Path(_resources.data_dir).parent)
    filters.reload_custom_filters()
    plugin_manager = BasePluginManager.get_instance()
    for plugin in plugin_manager.get_export_plugins():
        if extension == plugin.get_extension():
            export_function = plugin.get_export_function()
            result = export_function(db_handle, file_name, User(), options)
            if not result:
                abort(500)
            return file_name, "." + extension


class ExportersResource(ProtectedResource, GrampsJSONEncoder):
    """Exporters resource."""

    @use_args({}, location="query")
    def get(self, args: Dict) -> Response:
        """Get all available exporter attributes."""
        db_handle = get_db_handle()
        return self.response(200, get_exporters())


class ExporterResource(ProtectedResource, GrampsJSONEncoder):
    """Export resource."""

    @use_args({}, location="query")
    def get(self, args: Dict, extension: str) -> Response:
        """Get specific report attributes."""
        db_handle = get_db_handle()
        exporters = get_exporters(extension)
        if exporters == []:
            abort(404)
        return self.response(200, exporters[0])


class ExporterFileResource(ProtectedResource, GrampsJSONEncoder):
    """Export file resource."""

    @use_args(
        {
            "compress": fields.Boolean(missing=True),
            "current_year": fields.Integer(missing=None),
            "event": fields.Str(missing=None),
            "gramps_id": fields.Str(missing=None),
            "handle": fields.Str(missing=None),
            "include_children": fields.Boolean(missing=True),
            "include_individuals": fields.Boolean(missing=True),
            "include_marriages": fields.Boolean(missing=True),
            "include_media": fields.Boolean(missing=True),
            "include_places": fields.Boolean(missing=True),
            "include_witnesses": fields.Boolean(missing=True),
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
            "locale": fields.Str(missing=None),
            "note": fields.Str(missing=None),
            "person": fields.Str(missing=None),
            "private": fields.Boolean(missing=False),
            "reference": fields.Boolean(missing=False),
            "sequence": fields.Str(
                missing="privacy,living,person,event,note,reference"
            ),
            "translate_headers": fields.Boolean(missing=True),
            "years_after_death": fields.Integer(missing=0),
            "jwt": fields.String(required=False),
        },
        location="query",
    )
    def get(self, args: Dict, extension: str) -> Response:
        """Get export file."""
        db_handle = get_db_handle()
        exporters = get_exporters(extension)
        if exporters == []:
            abort(404)
        options = prepare_options(db_handle, args)
        file_name, file_type = run_export(db_handle, extension, options)
        buffer = get_buffer_for_file(file_name, delete=True)
        mime_type = "application/octet-stream"
        if file_type != ".pl" and file_type in mimetypes.types_map:
            mime_type = mimetypes.types_map[file_type]
        return send_file(buffer, mimetype=mime_type)


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
        # Referenced by third party ged2 export plugin
        self.include_witnesses = 1
        self.include_media = 1

    def get_custom_filter(self, name: str, namespace: str):
        """Get the named custom filter from a namespace."""
        filters.reload_custom_filters()
        for filter_class in filters.CustomFilters.get_filters(namespace):
            if name == filter_class.get_name():
                return filter_class
        raise ValueError(
            "can not find filter '%s' in namespace '%s'" % (name, namespace)
        )

    def set_person_filter(self, name: str, gramps_id: str):
        """Add the specified person filter."""
        self.gramps_id = gramps_id
        self.pfilter = filters.GenericFilter()
        if name == "Descendants":
            self.pfilter.set_name(_("Descendants of %s") % gramps_id)
            self.pfilter.add_rule(filters.rules.person.IsDescendantOf([gramps_id, 1]))
        elif name == "DescendantFamilies":
            self.pfilter.set_name(_("Descendant Families of %s") % gramps_id)
            self.pfilter.add_rule(
                filters.rules.person.IsDescendantFamilyOf([gramps_id, 1])
            )
        elif name == "Ancestors":
            self.pfilter.set_name(_("Ancestors of %s") % gramps_id)
            self.pfilter.add_rule(filters.rules.person.IsAncestorOf([gramps_id, 1]))
        elif name == "CommonAncestor":
            self.pfilter.set_name(_("People with common ancestor with %s") % gramps_id)
            self.pfilter.add_rule(
                filters.rules.person.HasCommonAncestorWith([gramps_id])
            )
        else:
            self.pfilter = self.get_custom_filter(name, "Person")

    def set_event_filter(self, name: str):
        """Add the specified event filter."""
        self.efilter = self.get_custom_filter(name, "Event")

    def set_note_filter(self, name: str):
        """Add the specified note filter."""
        self.nfilter = self.get_custom_filter(name, "Note")

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
    def get_filtered_database(self, dbase, progress=None):
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
                dbase = LivingProxyDb(
                    dbase,
                    self.living,
                    current_year=self.current_year,
                    years_after_death=self.years_after_death,
                    llocale=self.locale,
                )
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
