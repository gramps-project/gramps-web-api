#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020       Nick Hall
# Copyright (C) 2020-2023  Gary Griffin
# Copyright (C) 2023-2025  David Straub
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

"""DNA resources."""

from __future__ import annotations

from typing import Any, Union

from flask import abort
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib import Citation, Note, Person
from gramps.gen.relationship import get_relationship_calculator
from gramps.gen.utils.grampslocale import GrampsLocale
from webargs import fields, validate

from gramps_webapi.api.people_families_cache import CachePeopleFamiliesProxy
from gramps_webapi.types import Handle, ResponseReturnValue

from ...types import Handle
from ..util import get_db_handle, get_locale_for_language, use_args
from . import ProtectedResource
from .util import get_person_profile_for_handle

SIDE_UNKNOWN = "U"
SIDE_MATERNAL = "M"
SIDE_PATERNAL = "P"

Segment = dict[str, Union[float, int, str]]


class PersonDnaMatchesResource(ProtectedResource):
    """Resource for getting DNA match data for a person."""

    @use_args(
        {
            "locale": fields.Str(
                load_default=None, validate=validate.Length(min=2, max=5)
            ),
            "raw": fields.Bool(load_default=False),
        },
        location="query",
    )
    def get(self, args: dict, handle: str):
        """Get the DNA match data."""
        db_handle = CachePeopleFamiliesProxy(get_db_handle())

        try:
            person: Person | None = db_handle.get_person_from_handle(handle)
        except HandleError:
            abort(404)
        if person is None:
            abort(404)
            raise AssertionError  # for type checker

        db_handle.cache_people()
        db_handle.cache_families()

        locale = get_locale_for_language(args["locale"], default=True)

        matches = []
        for association_index, association in enumerate(person.get_person_ref_list()):
            if association.get_relation() == "DNA":
                match_data = get_match_data(
                    db_handle=db_handle,
                    person=person,
                    association_index=association_index,
                    locale=locale,
                    include_raw_data=args["raw"],
                )
                matches.append(match_data)
        return matches


class DnaMatchParserResource(ProtectedResource):
    """DNA match parser resource."""

    @use_args(
        {"string": fields.Str(required=True)},
        location="json",
    )
    def post(self, args: dict) -> ResponseReturnValue:
        """Parse DNA match string."""
        return parse_raw_dna_match_string(args["string"])


def get_match_data(
    db_handle: DbReadBase,
    person: Person,
    association_index: int,
    locale: GrampsLocale = glocale,
    include_raw_data: bool = False,
) -> dict[str, Any]:
    """Get the DNA match data in the appropriate format."""
    relationship = get_relationship_calculator(reinit=True, clocale=locale)
    association = person.get_person_ref_list()[association_index]
    associate = db_handle.get_person_from_handle(association.ref)
    data, _ = relationship.get_relationship_distance_new(
        db_handle,
        person,
        associate,
        all_families=False,
        all_dist=True,
        only_birth=True,
    )
    if data[0][0] <= 0:  # Unrelated
        side = SIDE_UNKNOWN
    elif data[0][0] == 1:  # parent / child
        if db_handle.get_person_from_handle(data[0][1]).gender == 0:
            side = SIDE_MATERNAL
        else:
            side = SIDE_PATERNAL
    elif (
        len(data) > 1 and data[0][0] == data[1][0] and data[0][2][0] != data[1][2][0]
    ):  # shares both parents
        side = SIDE_UNKNOWN
    else:
        translate_sides = {"m": SIDE_MATERNAL, "f": SIDE_PATERNAL}
        side = translate_sides[data[0][2][0]]

    segments = []

    # Get Notes attached to Association
    note_handles: list[Handle] = association.get_note_list()
    # we'll be building a list of notes that actually contain segment data
    note_handles_with_segments: list[Handle] = []

    # Get Notes attached to Citation which is attached to the Association
    for citation_handle in association.get_citation_list():
        try:
            citation: Citation = db_handle.get_citation_from_handle(citation_handle)
        except HandleError:
            continue
        if citation is not None:
            note_handles += citation.get_note_list()

    for note_handle in note_handles:
        note_segments = get_segments_from_note(db_handle, handle=note_handle, side=side)
        if note_segments:
            segments += note_segments
            note_handles_with_segments.append(note_handle)

    rel_strings, common_ancestors = relationship.get_all_relationships(
        db_handle, person, associate
    )
    if len(rel_strings) == 0:
        rel_string = ""
        ancestor_handles = []
    else:
        rel_string = rel_strings[0]
        ancestor_handles = list(dict.fromkeys(common_ancestors[0]))  # make unique
    ancestor_profiles = [
        get_person_profile_for_handle(
            db_handle=db_handle, handle=handle, args=[], locale=locale
        )
        for handle in ancestor_handles
    ]
    result = {
        "handle": association.ref,
        "segments": segments,
        "relation": rel_string,
        "ancestor_handles": ancestor_handles,
        "ancestor_profiles": ancestor_profiles,
        "person_ref_idx": association_index,
        "note_handles": note_handles_with_segments,
    }
    if include_raw_data:
        raw_data = []
        for note_handle in note_handles_with_segments:
            note: Note = db_handle.get_note_from_handle(note_handle)
            raw_data.append(note.get())
        result["raw_data"] = raw_data
    return result


def get_segments_from_note(
    db_handle: DbReadBase, handle: Handle, side: str | None = None
) -> list[Segment]:
    """Get the segements from a note handle."""
    try:
        note: Note | None = db_handle.get_note_from_handle(handle)
    except HandleError:
        return []
    if note is None:
        return []
    raw_string: str = note.get()
    return parse_raw_dna_match_string(raw_string, side=side)


def parse_raw_dna_match_string(
    raw_string: str, side: str | None = None
) -> list[Segment]:
    """Parse a raw DNA match string and return a list of segments."""
    segments = []
    for line in raw_string.split("\n"):
        data = parse_line(line, side=side)
        if data:
            segments.append(data)
    return segments


def parse_line(line: str, side: str | None = None) -> Segment | None:
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
    side = side or SIDE_UNKNOWN
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
