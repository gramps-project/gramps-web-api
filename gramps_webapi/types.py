#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2023      David Straub
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

"""Custom types."""

from __future__ import annotations

from pathlib import Path
from typing import Any, NewType, Protocol, Union

import flask.typing

Handle = NewType("Handle", str)
GrampsId = NewType("GrampsId", str)
FilenameOrPath = Union[str, Path]
TransactionJson = list[dict[str, Any]]
ResponseReturnValue = flask.typing.ResponseReturnValue
MatchSegment = dict[str, Union[float, int, str, None]]


class ProgressCallback(Protocol):
    """Protocol for progress callback functions."""

    def __call__(self, current: int, total: int, prev: int | None = None) -> None:
        """Call the progress callback with current progress, total items, and optional previous value."""
