#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

"""Translate API Resource."""

import json
from typing import Dict

from flask import Response, abort
from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.utils.grampslocale import GrampsLocale
from webargs import fields
from webargs.flaskparser import use_args

from . import ProtectedResource
from .emit import GrampsJSONEncoder


class TranslationResource(ProtectedResource, GrampsJSONEncoder):
    """Translation resource."""

    @use_args(
        {"strings": fields.Str(required=True)},
        location="query",
    )
    def get(self, args: Dict, isocode: str) -> Response:
        """Get translation."""
        try:
            strings = json.loads(args["strings"])
        except json.JSONDecodeError:
            abort(400)

        language_code = isocode.replace("-", "_")
        catalog = GRAMPS_LOCALE.get_language_dict()
        found = False
        for language in catalog:
            if catalog[language] == language_code:
                found = True
        if not found:
            abort(404)

        gramps_locale = GrampsLocale(lang=language_code)
        return self.response(
            200,
            [
                {"original": s, "translation": gramps_locale.translation.sgettext(s)}
                for s in strings
            ],
        )


class TranslationsResource(ProtectedResource, GrampsJSONEncoder):
    """Translations resource."""

    def get(self) -> Response:
        """Get available translations."""
        catalog = GRAMPS_LOCALE.get_language_dict()
        return self.response(
            200,
            [
                {"language": language, "isocode": catalog[language].replace("_", "-")}
                for language in catalog
            ],
        )
