"""Utility functions for DNA data."""

from gramps_webapi.types import MatchSegment

SIDE_UNKNOWN = "U"
SIDE_MATERNAL = "M"
SIDE_PATERNAL = "P"


def parse_raw_dna_match_string(raw_string: str) -> list[MatchSegment]:
    """Parse a raw DNA match string."""
    segments = []
    for line in raw_string.split("\n"):
        data = parse_line(line)
        if data:
            segments.append(data)
    return segments


def parse_line(line: str) -> MatchSegment | None:
    """Parse a line from the CSV/TSV data and return a dictionary."""
    if "\t" in line:
        # Tabs are the field separators. Now determine THOUSEP and RADIXCHAR.
        # Use Field 2 (Stop Pos) to see if there are THOUSEP there. Use Field 3
        # (SNPs) to see if there is a radixchar
        field = line.split("\t")
        if "," in field[2]:
            line = line.replace(",", "")
        elif "." in field[2]:
            line = line.replace(".", "")
        if "," in field[3]:
            line = line.replace(",", ".")
        line = line.replace("\t", ",")
    field = line.split(",")
    if len(field) < 4:
        return None
    chromo = field[0].strip()
    start = get_base(field[1])
    stop = get_base(field[2])
    try:
        cms = float(field[3])
    except (ValueError, TypeError, IndexError):
        return None
    try:
        snp = int(field[4])
    except (ValueError, TypeError, IndexError):
        snp = 0
    seg_comment = ""
    side = SIDE_UNKNOWN
    if len(field) > 5:
        if field[5] in {SIDE_MATERNAL, SIDE_PATERNAL, SIDE_UNKNOWN}:
            side = field[5].strip()
        else:
            seg_comment = field[5].strip()
    return {
        "chromosome": chromo,
        "start": start,
        "stop": stop,
        "side": side,
        "cM": cms,
        "SNPs": snp,
        "comment": seg_comment,
    }


def get_base(num: str) -> int:
    """Get the number as int."""
    try:
        return int(num)
    except (ValueError, TypeError):
        try:
            return int(float(num) * 1000000)
        except (ValueError, TypeError):
            return 0
