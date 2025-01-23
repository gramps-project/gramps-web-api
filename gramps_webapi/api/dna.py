"""Utility functions for DNA data."""

from __future__ import annotations

import re

from gramps_webapi.types import MatchSegment

SIDE_UNKNOWN = "U"
SIDE_MATERNAL = "M"
SIDE_PATERNAL = "P"


def get_delimiter(rows: list[str]) -> str:
    """Guess the delimiter of a string containing a CSV-like table.

    It is assumed that the table has at least 4 columns and at least one
    row.
    """
    if rows[0].count("\t") >= 3:
        return "\t"
    if rows[0].count(",") >= 3:
        return ","
    if rows[0].count(";") >= 3:
        return ";"
    raise ValueError("Could not determine delimiter.")


def is_numeric(value: str) -> bool:
    """Determine if a string is number-like."""
    if value == "":
        return False
    try:
        float(value)
        return True
    except ValueError:
        pass
    if re.match(r"^\d[\d\.,]*$", value):
        return True
    return False


def has_header(rows: list[str], delimiter: str) -> bool:
    """Determine if the table has a header."""
    if len(rows) < 2:
        return False
    header = rows[0]
    if len(header) < 4:
        return False
    header_columns = header.split(delimiter)
    if any(is_numeric(column) for column in header_columns):
        return False
    return True


def get_order(header: list[str]) -> list[int]:
    """Get the order of the columns."""
    return [0, 1, 2, 3, 4, 5]


def parse_raw_dna_match_string(raw_string: str) -> list[MatchSegment]:
    """Parse a raw DNA match string."""
    rows = raw_string.strip().split("\n")
    try:
        delimiter = get_delimiter(rows)
    except ValueError:
        return []
    if has_header(rows, delimiter):
        header = rows[0].split(delimiter)
        order = get_order(header)
        rows = rows[1:]
    else:
        order = list(range(6))
    segments = []
    for row in rows:
        if row.strip() == "":
            continue
        try:
            data = process_row(fields=row.split(delimiter), order=order)
        except (ValueError, TypeError):
            continue
        if data:
            segments.append(data)
    return segments


def cast_int(value: str) -> int:
    """Cast a string to an integer."""
    try:
        return int(value.replace(",", "").replace(".", ""))
    except (ValueError, TypeError):
        return 0


def cast_float(value: str) -> float:
    """Cast a string to a float."""
    try:
        return float(value)
    except ValueError:
        return 0.0


def process_row(fields: list[str], order: list[int]) -> MatchSegment | None:
    """Process a row of a DNA match table."""
    if len(fields) < 4:
        return None
    try:
        chromo = fields[order[0]].strip()
        start = cast_int(fields[order[1]].strip())
        stop = cast_int(fields[order[2]].strip())
        cms = cast_float(fields[order[3]].strip())
        if len(fields) > 4:
            snp = cast_int(fields[order[4]].strip())
        else:
            snp = 0
        if len(fields) > 5:
            seg_comment = fields[order[5]].strip()
        else:
            seg_comment = ""
    except (ValueError, TypeError):
        return None
    return {
        "chromosome": chromo,
        "start": start,
        "stop": stop,
        "side": "U",
        "cM": cms,
        "SNPs": snp,
        "comment": seg_comment,
    }
