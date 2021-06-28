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

"""Citation API resource."""

from typing import Dict

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.lib import Citation
from gramps.gen.utils.grampslocale import GrampsLocale

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import (
    get_citation_profile_for_object,
    get_extended_attributes,
    get_source_by_handle,
)


class CitationResourceHelper(GrampsObjectResourceHelper):
    """Citation resource helper."""

    gramps_class_name = "Citation"

    def object_extend(
        self, obj: Citation, args: Dict, locale: GrampsLocale = glocale
    ) -> Citation:
        """Extend citation attributes as needed."""
        if "profile" in args:
            obj.profile = get_citation_profile_for_object(
                self.db_handle, obj, args["profile"]
            )
        if "extend" in args:
            obj.extended = get_extended_attributes(self.db_handle, obj, args)
            if "all" in args["extend"] or "source_handle" in args["extend"]:
                obj.extended["source"] = get_source_by_handle(
                    self.db_handle, obj.source_handle, args
                )
        return obj


class CitationResource(GrampsObjectProtectedResource, CitationResourceHelper):
    """Citation resource."""


class CitationsResource(GrampsObjectsProtectedResource, CitationResourceHelper):
    """Citations resource."""
