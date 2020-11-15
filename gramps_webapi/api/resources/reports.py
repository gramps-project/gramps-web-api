"""Reports Plugin API resource."""

import io
import json
import os
import uuid
from mimetypes import types_map
from pathlib import Path
from typing import BinaryIO, Dict

from flask import Response, abort, send_file
from gramps.cli.plug import CommandLineReport, cl_report
from gramps.gen.db.base import DbReadBase
from gramps.gen.filters import reload_custom_filters
from gramps.gen.plug import BasePluginManager
from gramps.gen.utils.resourcepath import ResourcePath
from webargs import fields, validate
from webargs.flaskparser import use_args

from ...const import REPORT_DEFAULTS, REPORT_FILTERS
from ..util import get_dbstate
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
        "id": report_data.id,
        "name": report_data.name,
        "name_accell": report_data.name_accell,
        "description": report_data.description,
        "version": report_data.version,
        "status": report_data.status,
        "fname": report_data.fname,
        "fpath": report_data.fpath,
        "ptype": report_data.ptype,
        "authors": report_data.authors,
        "authors_email": report_data.authors_email,
        "supported": report_data.supported,
        "load_on_reg": report_data.load_on_reg,
        "icons": report_data.icons,
        "icondir": icondir,
        "category": report_data.category,
        "module": report_data.mod_name,
        "reportclass": report_data.reportclass,
        "require_active": report_data.require_active,
        "report_modes": report_data.report_modes,
        "option_class": report_data.optionclass,
        "options_dict": report.options_dict,
        "options_help": options_help,
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
            file_name = str(uuid.uuid4()) + file_type
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
        buffer = fetch_buffer(file_name)
        return send_file(buffer, mimetype=types_map[file_type])
