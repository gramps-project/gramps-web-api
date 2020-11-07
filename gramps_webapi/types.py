"""Custom types."""

from pathlib import Path
from typing import NewType, Union

Handle = NewType("Handle", str)
GrampsId = NewType("GrampsId", str)
FilenameOrPath = Union[str, Path]
