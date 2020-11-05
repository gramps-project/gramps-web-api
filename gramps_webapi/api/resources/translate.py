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
