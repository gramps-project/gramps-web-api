"""Metadata API resource."""

from typing import Dict

import yaml
from flask import Response
from gramps.cli.clidbman import CLIDbManager
from gramps.gen.config import get, get_section_settings, get_sections
from gramps.gen.const import ENV, GRAMPS_LOCALE
from gramps.gen.db.base import DbReadBase
from pkg_resources import resource_filename

from gramps_webapi.const import VERSION

from ..util import get_dbstate
from . import ProtectedResource
from .emit import GrampsJSONEncoder


def get_config() -> Dict:
    """Get the Gramps configuration options."""
    config = {}
    for section in get_sections():
        data = {}
        for setting in get_section_settings(section):
            key = section + "." + setting
            value = get(key)
            data.update({key: value})
        config.update({section: data})
    return config


class MetadataResource(ProtectedResource, GrampsJSONEncoder):
    """Metadata resource."""

    @property
    def db_handle(self) -> DbReadBase:
        """Get the database instance."""
        return get_dbstate().db

    def get(self) -> Response:
        """Get active database and application related metadata information."""
        db_handle = self.db_handle
        db_name = db_handle.get_dbname()
        for data in CLIDbManager(get_dbstate()).family_tree_summary():
            for item in data:
                if item == "Family Tree" and data[item] == db_name:
                    db_type = data["Database"]
                    break

        with open(
            resource_filename("gramps_webapi", "data/apispec.yaml")
        ) as file_handle:
            schema = yaml.safe_load(file_handle)

        result = {
            "database": {
                "id": db_handle.get_dbid(),
                "name": db_name,
                "savepath": db_handle.get_save_path(),
                "type": db_type,
            },
            "default_person": db_handle.get_default_handle(),
            "gramps": {"config": get_config(), "env": ENV},
            "gramps_webapi": {
                "schema_version": schema["info"]["version"],
                "version": VERSION,
            },
            "locale": {
                "lang": GRAMPS_LOCALE.lang,
                "localedir": GRAMPS_LOCALE.localedir,
                "localedomain": GRAMPS_LOCALE.localedomain,
            },
            "mediapath": db_handle.get_mediapath(),
            "object_counts": {},
            "researcher": db_handle.get_researcher(),
            "surnames": db_handle.get_surname_list(),
        }
        data = db_handle.get_summary()
        for item in data:
            key = item.replace(" ", "_").lower()
            if "database" in key or "schema" in key:
                key = key.replace("database_", "")
                result["database"].update({key: data[item]})
            elif "number_of" in key:
                key = key.replace("number_of_", "")
                result["object_counts"].update({key: data[item]})
            else:
                result[key] = data[item]
        return self.response(200, result)
