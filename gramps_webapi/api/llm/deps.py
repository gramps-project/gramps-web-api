#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2025      David Straub
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

"""Dependencies for Pydantic AI agent."""

from collections.abc import Callable
from dataclasses import dataclass, field

from gramps.gen.db import DbTxn
from gramps.gen.db.base import DbWriteBase

from ...types import TransactionJson

# a change to the database, applied within a transaction
Change = Callable[[DbWriteBase, DbTxn], None]


@dataclass
class Proposal:
    """Changes proposed by the agent, awaiting the user's approval."""

    changes: list[Change] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)
    # dry run of all changes, replayed when the user approves them
    transaction: TransactionJson = field(default_factory=list)


@dataclass
class AgentDeps:
    """Dependencies for the Pydantic AI agent."""

    tree: str
    include_private: bool
    max_context_length: int
    user_id: str
    progress_callback: Callable[[str, str], None] | None = field(default=None)
    # None unless the agent may propose changes
    proposal: Proposal | None = field(default=None)
