#
# Gramps Web API - A RESTful API for the Gramps genealogy program
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

"""Reports Plugin API resource."""

import json
import os
import uuid
from mimetypes import types_map
from pathlib import Path
from typing import Dict

from flask import Response, abort, current_app, send_file
from gramps.cli.plug import CommandLineReport, cl_report
from gramps.gen.const import TEMP_DIR
from gramps.gen.db.base import DbReadBase
from gramps.gen.filters import reload_custom_filters
from gramps.gen.plug import BasePluginManager
from gramps.gen.utils.resourcepath import ResourcePath
from webargs import fields, validate
from webargs.flaskparser import use_args

from ...const import REPORT_DEFAULTS, REPORT_FILTERS
from ..util import get_buffer_for_file, get_dbstate
from . import ProtectedResource
from .emit import GrampsJSONEncoder

_EXTENSION_MAP = {".gvpdf": ".pdf", ".gspdf": ".pdf"}


def get_report_profile(
    db_handle: DbReadBase, plugin_manager: BasePluginManager, report_data
):
    """Extract and return report attributes and options."""
    module = plugin_manager.load_plugin(report_data)
    option_class = getattr(module, report_data.optionclass)
    report = CommandLineReport(
        db_handle, report_data.name, report_data.category, option_class, {}
    )
    icondir = report_data.icondir or ""
    options_help = report.options_help
    if REPORT_FILTERS:
        for report_type in REPORT_FILTERS:
            for item in options_help["off"][2]:
                if item[: len(report_type)] == report_type:
                    del options_help["off"][2][options_help["off"][2].index(item)]
                    break
    return {
        "authors": report_data.authors,
        "authors_email": report_data.authors_email,
        "category": report_data.category,
        "description": report_data.description,
        "id": report_data.id,
        "name": report_data.name,
        "options_dict": report.options_dict,
        "options_help": options_help,
        "report_modes": report_data.report_modes,
        "version": report_data.version,
    }


def get_reports(db_handle: DbReadBase, report_id: str = None):
    """Extract and return report attributes and options."""
    reload_custom_filters()
    plugin_manager = BasePluginManager.get_instance()
    reports = []
    for report_data in plugin_manager.get_reg_reports(gui=False):
        if report_id is not None and report_data.id != report_id:
            continue
        if report_data.category not in REPORT_DEFAULTS:
            continue
        report = get_report_profile(db_handle, plugin_manager, report_data)
        reports.append(report)
    return reports


def run_report(
    db_handle: DbReadBase,
    report_id: str,
    report_options: Dict,
    allow_file: bool = False,
):
    """Generate the report."""
    if "off" in report_options and report_options["off"] in REPORT_FILTERS:
        abort(422)
    _resources = ResourcePath()
    os.environ["GRAMPS_RESOURCES"] = str(Path(_resources.data_dir).parent)
    reload_custom_filters()
    plugin_manager = BasePluginManager.get_instance()
    for report_data in plugin_manager.get_reg_reports(gui=False):
        if report_data.id == report_id:
            if report_data.category not in REPORT_DEFAULTS:
                abort(404)
            if "off" not in report_options:
                report_options["off"] = REPORT_DEFAULTS[report_data.category]
            file_type = "." + report_options["off"]
            file_type = _EXTENSION_MAP.get(file_type) or file_type
            report_path = TEMP_DIR
            if current_app.config.get("REPORT_PATH"):
                report_path = current_app.config.get("REPORT_PATH")
            file_name = os.path.join(
                report_path, "{}{}".format(uuid.uuid4(), file_type)
            )
            report_options["of"] = file_name
            report_profile = get_report_profile(db_handle, plugin_manager, report_data)
            validate_options(report_profile, report_options, allow_file=allow_file)
            module = plugin_manager.load_plugin(report_data)
            option_class = getattr(module, report_data.optionclass)
            report_class = getattr(module, report_data.reportclass)
            cl_report(
                db_handle,
                report_data.name,
                report_data.category,
                report_class,
                option_class,
                report_options,
            )
            return file_name, file_type
    abort(404)


def validate_options(report: Dict, report_options: Dict, allow_file: bool = False):
    """Check validity of provided report options."""
    if report["id"] == "familylines_graph":
        if "gidlist" not in report_options or not report_options["gidlist"]:
            abort(422)
    for option in report_options:
        if option not in report["options_dict"]:
            abort(422)
        if isinstance(report["options_help"][option][2], type([])):
            option_list = []
            for item in report["options_help"][option][2]:
                if "\t" in item:
                    option_list.append(item.split("\t")[0])
                else:
                    option_list.append(item)
            if report_options[option] not in option_list:
                abort(422)
            continue
        if not isinstance(report_options[option], str):
            abort(422)
        if "A number" in report["options_help"][option][2]:
            try:
                int(report_options[option])
            except ValueError:
                abort(422)
        if "Size in cm" in report["options_help"][option][2]:
            try:
                float(report_options[option])
            except ValueError:
                abort(422)


class ReportsResource(ProtectedResource, GrampsJSONEncoder):
    """Reports resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    @use_args({}, location="query")
    def get(self, args: Dict) -> Response:
        """Get all available report attributes."""
        reports = get_reports(self.db_handle)
        return self.response(200, reports)


class ReportResource(ProtectedResource, GrampsJSONEncoder):
    """Report resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    @use_args({}, location="query")
    def get(self, args: Dict, report_id: str) -> Response:
        """Get specific report attributes."""
        reports = get_reports(self.db_handle, report_id=report_id)
        if reports == []:
            abort(404)
        return self.response(200, reports[0])


class ReportRunnerResource(ProtectedResource, GrampsJSONEncoder):
    """Report runner resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    @use_args(
        {
            "options": fields.Str(validate=validate.Length(min=1)),
        },
        location="query",
    )
    def get(self, args: Dict, report_id: str) -> Response:
        """Get specific report attributes."""
        report_options = {}
        if "options" in args:
            try:
                report_options = json.loads(args["options"])
            except json.JSONDecodeError:
                abort(400)
        if "of" in report_options:
            abort(422)

        file_name, file_type = run_report(self.db_handle, report_id, report_options)
        buffer = get_buffer_for_file(file_name)
        return send_file(buffer, mimetype=types_map[file_type])
