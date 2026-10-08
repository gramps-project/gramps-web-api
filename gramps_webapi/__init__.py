#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020      David Straub
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

import os

# Gramps sets its locale from the environment when first imported. The API
# translates into the language requested by the client, so the server locale
# is always English. LANGUAGE takes precedence over LANG and LC_* for
# translations and dates; the collation (LC_COLLATE) is left alone.
os.environ["LANGUAGE"] = "en"

from ._version import __version__  # noqa: E402
