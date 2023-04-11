#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      Christopher Horn
# Copyright (C) 2023      David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#

"""Functions for running Gramps reports."""

import os
import uuid
from pathlib import Path
from typing import Dict, Optional

from flask import abort, current_app
from gramps.cli.plug import CommandLineReport
from gramps.cli.user import User
from gramps.gen.db.base import DbReadBase
from gramps.gen.filters import reload_custom_filters
from gramps.gen.plug import BasePluginManager
from gramps.gen.plug.docgen import PaperStyle
from gramps.gen.plug.report import (
    CATEGORY_BOOK,
    CATEGORY_DRAW,
    CATEGORY_GRAPHVIZ,
    CATEGORY_TEXT,
    CATEGORY_TREE,
)
from gramps.gen.utils.grampslocale import GrampsLocale
from gramps.gen.utils.resourcepath import ResourcePath

from ..const import MIME_TYPES, REPORT_DEFAULTS, REPORT_FILTERS

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


def check_report_id_exists(report_id: str) -> bool:
    """Check if a report ID exists."""
    reload_custom_filters()
    plugin_manager = BasePluginManager.get_instance()
    for report_data in plugin_manager.get_reg_reports(gui=False):
        if report_data.id == report_id:
            return True
    return False


def cl_report_new(
    database,
    name,
    category,
    report_class,
    options_class,
    options_str_dict,
    language: Optional[str] = None,
):
    """Run the selected report.

    Derived from gramps.cli.plug.cl_report.
    """
    clr = CommandLineReport(database, name, category, options_class, options_str_dict)
    if category in [CATEGORY_TEXT, CATEGORY_DRAW, CATEGORY_BOOK]:
        if clr.doc_options:
            clr.option_class.handler.doc = clr.format(
                clr.selected_style,
                PaperStyle(
                    clr.paper,
                    clr.orien,
                    clr.marginl,
                    clr.marginr,
                    clr.margint,
                    clr.marginb,
                ),
                clr.doc_options,
            )
        else:
            clr.option_class.handler.doc = clr.format(
                clr.selected_style,
                PaperStyle(
                    clr.paper,
                    clr.orien,
                    clr.marginl,
                    clr.marginr,
                    clr.margint,
                    clr.marginb,
                ),
            )
    elif category in [CATEGORY_GRAPHVIZ, CATEGORY_TREE]:
        clr.option_class.handler.doc = clr.format(
            clr.option_class,
            PaperStyle(
                clr.paper,
                clr.orien,
                clr.marginl,
                clr.marginr,
                clr.margint,
                clr.marginb,
            ),
        )
    if clr.css_filename is not None and hasattr(
        clr.option_class.handler.doc, "set_css_filename"
    ):
        clr.option_class.handler.doc.set_css_filename(clr.css_filename)
    my_report = report_class(database, clr.option_class, User())
    my_report.set_locale(language or GrampsLocale.DEFAULT_TRANSLATION_STR)
    my_report.doc.init()
    my_report.begin_report()
    my_report.write_report()
    my_report.end_report()
    return clr


def run_report(
    db_handle: DbReadBase,
    report_id: str,
    report_options: Dict,
    allow_file: bool = False,
    language: Optional[str] = None,
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
            if file_type not in MIME_TYPES:
                current_app.logger.error(f"Cannot find {file_type} in MIME_TYPES")
                abort(500)
            report_path = current_app.config.get("REPORT_DIR")
            os.makedirs(report_path, exist_ok=True)
            file_name = f"{uuid.uuid4()}{file_type}"
            report_options["of"] = os.path.join(report_path, file_name)
            report_profile = get_report_profile(db_handle, plugin_manager, report_data)
            validate_options(report_profile, report_options, allow_file=allow_file)
            module = plugin_manager.load_plugin(report_data)
            option_class = getattr(module, report_data.optionclass)
            report_class = getattr(module, report_data.reportclass)
            cl_report_new(
                db_handle,
                report_data.name,
                report_data.category,
                report_class,
                option_class,
                report_options,
                language=language,
            )
            if (
                file_type == ".dot"
                and not os.path.isfile(report_options["of"])
                and os.path.isfile(report_options["of"] + ".gv")
            ):
                file_type = ".gv"
                file_name = f"{file_name}.gv"
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
                # Some option specs include a comment part after a tab, e.g. to give
                # the name of a family associated with a family ID. It's the part
                # before the tab that's a valid value.
                # Some tab-separated specs also have a colon before the tab.
                option_list.append(item.split("\t")[0].rstrip(":"))
            if report_options[option] not in option_list:
                abort(422)
            continue
        if not isinstance(report_options[option], str):
            abort(422)
        if "A number" in report["options_help"][option][2]:
            try:
                float(report_options[option])
            except ValueError:
                abort(422)
        if "Size in cm" in report["options_help"][option][2]:
            try:
                float(report_options[option])
            except ValueError:
                abort(422)
