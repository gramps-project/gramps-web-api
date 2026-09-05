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

"""Repository API resource."""

from typing import Dict

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.lib import Repository
from gramps.gen.utils.grampslocale import GrampsLocale

from .base import (
    GrampsObjectProtectedResource,
    GrampsObjectResourceHelper,
    GrampsObjectsProtectedResource,
)
from .util import get_repository_profile_for_object



class RepositoryResourceHelper(GrampsObjectResourceHelper):
    """Repository resource helper."""

    gramps_class_name = "Repository"

    def object_extend(
        self, obj: Repository, args: Dict, locale: GrampsLocale = glocale
    ) -> Repository:
        """Extend repository attributes as needed."""
        if "profile" in args:
            obj.profile = get_repository_profile_for_object(
                self.db_handle, obj, args["profile"], locale=locale
            )
        return super().object_extend(obj, args, locale=locale)


class RepositoryResource(GrampsObjectProtectedResource, RepositoryResourceHelper):
    """Repository resource."""


class RepositoriesResource(GrampsObjectsProtectedResource, RepositoryResourceHelper):
    """Repositories resource."""
