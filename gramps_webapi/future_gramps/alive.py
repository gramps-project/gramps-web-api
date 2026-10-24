#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2000-2007  Donald N. Allingham
# Copyright (C) 2026       Gramps Development Team
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

"""Keep private records out of probably alive estimates.

Backport of https://github.com/gramps-project/gramps/pull/2565 to the
Gramps version currently pinned by Gramps Web API. The functions below are
copied verbatim from that PR and replace or extend the ones in
`gramps.gen.utils.alive` by `apply_patch`.

`probably_alive_range` removes all proxies from the database it is given,
so that the estimate can use people that a proxy such as `LivingProxyDb`
hides. Without the fix, this also removes `PrivateProxyDb`, so an estimate
made for someone who must not see private records is based on them
anyway, and the related person it returns is the full stored record.
`probably_alive` and the `ProbablyAlive` filter rule call
`probably_alive_range` through the module, so the patch covers them, and
everything that calls them, too.

Remove this module once the pinned Gramps version contains the fix.
"""

from gramps.gen.db.base import DbReadBase
from gramps.gen.proxy.private import PrivateProxyDb, sanitize_person
from gramps.gen.proxy.proxybase import ProxyDbBase
from gramps.gen.utils import alive


def probably_alive_range(
    person, db, max_sib_age_diff=None, max_age_prob_alive=None, avg_generation_gap=None
):
    """
    Computes estimated birth and death date ranges.
    Returns: (birth_date, death_date, explain_text, related_person)
    """
    alive_db = get_alive_db(db)
    if person is not None and isinstance(alive_db, PrivateProxyDb):
        # the caller may have passed a person with private parts
        if person.get_privacy():
            person = None
        else:
            person = sanitize_person(alive_db.db, person)
    # Now, we create a wrapper for doing work:
    pbac = alive.ProbablyAlive(
        alive_db, max_sib_age_diff, max_age_prob_alive, avg_generation_gap
    )
    return pbac.probably_alive_range(person)


def get_alive_db(db: DbReadBase) -> DbReadBase:
    """
    Return the database to base probably alive estimates on.

    All proxies are removed so that everyone in the database can be used,
    but if one of them hides private records, they stay hidden.
    """
    basedb = db
    private = False
    while isinstance(basedb, ProxyDbBase):
        private = private or isinstance(basedb, PrivateProxyDb)
        basedb = basedb.db
    if private:
        return PrivateProxyDb(basedb)
    return basedb


def apply_patch() -> None:
    """Patch Gramps' probably_alive_range, unless it already has the fix."""
    if hasattr(alive, "get_alive_db"):
        return
    alive.get_alive_db = get_alive_db
    alive.probably_alive_range = probably_alive_range
