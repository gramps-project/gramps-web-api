"""Translation API Resource."""

import json
from typing import List

from flask import abort
from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.utils.grampslocale import GrampsLocale
from webargs import fields
from webargs.flaskparser import use_args

from . import ProtectedResource
from .emit import GrampsJSONEncoder


class TranslationResource(ProtectedResource, GrampsJSONEncoder):
    """Translation resource."""

    @use_args(
        {"strings": fields.Str(), "lang": fields.Str()},
        location="query",
    )
    def get(self, args):
        """Get translation."""
        if "strings" not in args:
            return self.response(GRAMPS_LOCALE.get_language_dict())

        try:
            strings = json.loads(args["strings"])
        except:
            abort(400)
        if "lang" in args and args["lang"] is not None:
            gramps_locale = GrampsLocale(lang=args["lang"])
        else:
            gramps_locale = GRAMPS_LOCALE
        return self.response(
            {s: gramps_locale.translation.sgettext(s) for s in strings}
        )
