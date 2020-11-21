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

"""Metadata API resource."""

import yaml
from flask import Response, abort
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.const import ENV, GRAMPS_LOCALE
from gramps.gen.db.base import DbReadBase
from gramps.gen.utils.grampslocale import INCOMPLETE_TRANSLATIONS, GrampsLocale
from pkg_resources import resource_filename

from gramps_webapi.const import VERSION

from ..util import get_dbstate
from . import ProtectedResource
from .emit import GrampsJSONEncoder


class MetadataResource(ProtectedResource, GrampsJSONEncoder):
    """Metadata resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get(self) -> Response:
        """Get active database and application related metadata information."""
        catalog = GRAMPS_LOCALE.get_language_dict()
        languages = {catalog[entry]: entry for entry in catalog}
        if GRAMPS_LOCALE.lang in languages:
            language = GRAMPS_LOCALE.lang
        elif GRAMPS_LOCALE.lang[:2] in languages:
            language = GRAMPS_LOCALE.lang[:2]
        else:
            abort(500)

        db_handle = self.db_handle
        db_name = db_handle.get_dbname()
        db_type = "Unknown"
        db_summary = CLIDbManager(get_dbstate()).family_tree_summary(
            database_names=[db_name]
        )
        if len(db_summary) == 1:
            db_key = GrampsLocale(lang=language).translation.sgettext("Database")
            for key in db_summary[0]:
                if key == db_key:
                    db_type = db_summary[0][key]

        with open(
            resource_filename("gramps_webapi", "data/apispec.yaml")
        ) as file_handle:
            schema = yaml.safe_load(file_handle)

        result = {
            "database": {
                "id": db_handle.get_dbid(),
                "name": db_name,
                "type": db_type,
            },
            "default_person": db_handle.get_default_handle(),
            "gramps": {
                "version": ENV["VERSION"],
            },
            "gramps_webapi": {
                "schema": schema["info"]["version"],
                "version": VERSION,
            },
            "locale": {
                "locale": GRAMPS_LOCALE.lang,
                "language": language,
                "description": GRAMPS_LOCALE._get_language_string(GRAMPS_LOCALE.lang),
                "incomplete_translation": bool(language in INCOMPLETE_TRANSLATIONS),
            },
            "object_counts": {
                "people": db_handle.get_number_of_people(),
                "families": db_handle.get_number_of_families(),
                "sources": db_handle.get_number_of_sources(),
                "citations": db_handle.get_number_of_citations(),
                "events": db_handle.get_number_of_events(),
                "media": db_handle.get_number_of_media(),
                "places": db_handle.get_number_of_places(),
                "repositories": db_handle.get_number_of_repositories(),
                "notes": db_handle.get_number_of_notes(),
                "tags": db_handle.get_number_of_tags(),
            },
            "researcher": db_handle.get_researcher(),
            "surnames": db_handle.get_surname_list(),
        }
        data = db_handle.get_summary()
        db_version_key = GrampsLocale(lang=language).translation.sgettext(
            "Database version"
        )
        db_module_key = GrampsLocale(lang=language).translation.sgettext(
            "Database module version"
        )
        db_schema_key = GrampsLocale(lang=language).translation.sgettext(
            "Schema version"
        )
        for item in data:
            if item == db_version_key:
                result["database"]["version"] = data[item]
            elif item == db_module_key:
                result["database"]["module"] = data[item]
            elif item == db_schema_key:
                result["database"]["schema"] = data[item]
        return self.response(200, result)
