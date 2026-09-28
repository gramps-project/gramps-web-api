#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026       David Straub
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
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

"""Patches of Gramps core that are already proposed for a future Gramps version.

Changes that belong in Gramps core, but should land in Gramps Web API
before the next Gramps release, live here as patches of the currently
pinned Gramps version, with a matching PR opened against Gramps core.
Each patch is removed once a Gramps release containing it is pinned.

Unlike the rest of Gramps Web API (AGPL), this subpackage is licensed
under the GPL, version 2 or later, like Gramps itself, so its code can
move into Gramps core unchanged.

See https://gramps.discourse.group/t/proposal-process-for-upstreaming-web-api-improvements-into-gramps-core/9940
"""

from . import relationship


def apply_patches() -> None:
    """Apply all patches to Gramps core."""
    # https://github.com/gramps-project/gramps/pull/2526
    relationship.apply_patch()
