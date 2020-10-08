"""Languages API Resource."""

from gramps.gen.utils.grampslocale import _LOCALE_NAMES

from . import ProtectedResource
from .emit import GrampsJSONEncoder


class LanguageResource(ProtectedResource, GrampsJSONEncoder):
    """Languages resource."""

    def get(self):
        """Return available languages."""
        return self.response({"data": _LOCALE_NAMES})
