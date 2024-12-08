#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
# Copyright (C) 2020      Christopher Horn
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

"""Translate API Resource."""

import json
from typing import Dict, List, Union

from flask import Response, abort
from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.utils.grampslocale import GrampsLocale
from webargs import fields, validate

from ..util import abort_with_message, get_locale_for_language, use_args
from . import ProtectedResource
from .emit import GrampsJSONEncoder


class Sort:
    """Class for extracting translation sort keys."""

    def __init__(self, default_locale=GRAMPS_LOCALE, current_locale=GRAMPS_LOCALE):
        """Initialize sort class."""
        self.default_locale = default_locale
        self.current_locale = current_locale

    def get_language_key(self, data):
        """Return sort key for language."""
        return self.default_locale.sort_key(data["language"])

    def get_default_key(self, data):
        """Return sort key for default locale."""
        return self.default_locale.sort_key(data["default"])

    def get_current_key(self, data):
        """Return sort key for current locale."""
        return self.current_locale.sort_key(data["current"])

    def get_native_key(self, data):
        """Return sort key for native locale."""
        native_locale = GrampsLocale(lang=data["language"])
        return native_locale.sort_key(data["native"])


class TranslationResource(ProtectedResource, GrampsJSONEncoder):
    """Translation resource."""

    @use_args(
        {"strings": fields.Str(required=True)},
        location="query",
    )
    def get(self, args: Dict, language: str) -> Response:
        """Get translation."""
        try:
            strings = json.loads(args["strings"])
        except json.JSONDecodeError:
            abort_with_message(400, "Error parsing strings")
        return self._get_or_post(strings=strings, language=language)

    @use_args(
        {"strings": fields.List(fields.Str, required=True)},
        location="json",
    )
    def post(self, args: Dict, language: str) -> Response:
        """Get translation for posted strings."""
        return self._get_or_post(strings=args["strings"], language=language)

    def _get_or_post(self, strings: List[str], language: str) -> Response:
        """Get translation."""
        catalog = GRAMPS_LOCALE.get_language_dict()
        for entry in catalog:
            if catalog[entry] == language:
                gramps_locale = GrampsLocale(lang=language)
                return self.response(
                    200,
                    [
                        {
                            "original": s,
                            "translation": gramps_locale.translation.sgettext(s),
                        }
                        for s in strings
                    ],
                )
        abort(404)


class TranslationsResource(ProtectedResource, GrampsJSONEncoder):
    """Translations resource."""

    @use_args(
        {
            "locale": fields.Str(
                load_default=None, validate=validate.Length(min=1, max=5)
            ),
            "sort": fields.DelimitedList(fields.Str(validate=validate.Length(min=1))),
        },
        location="query",
    )
    def get(self, args: dict) -> Response:
        """Get available translations."""
        default_locale = GrampsLocale(lang="en")
        current_locale = get_locale_for_language(args["locale"], default=True)
        catalog = default_locale.get_language_dict()
        translations = []
        for entry in catalog:
            native_locale = GrampsLocale(lang=catalog[entry])
            translations.append(
                {
                    "default": entry,
                    "current": current_locale.translation.sgettext(entry),
                    "language": catalog[entry],
                    "native": native_locale.translation.sgettext(entry),
                }
            )

        sort = Sort(default_locale=default_locale, current_locale=current_locale)
        lookup = {
            "current": sort.get_current_key,
            "default": sort.get_default_key,
            "language": sort.get_language_key,
            "native": sort.get_native_key,
        }

        if "sort" not in args:
            args["sort"] = ["language"]
        for sort_key in args["sort"]:
            sort_key = sort_key.strip()
            reverse = False
            if sort_key[:1] == "-":
                reverse = True
                sort_key = sort_key[1:]
            if sort_key not in lookup:
                abort(422)
            translations.sort(key=lambda x: lookup[sort_key](x), reverse=reverse)

        return self.response(200, translations)
