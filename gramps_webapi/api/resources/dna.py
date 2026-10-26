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

from typing import Any

from flask import abort
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib import Citation, Note, Person
from gramps.gen.relationship import get_relationship_calculator
from gramps.gen.utils.grampslocale import GrampsLocale
from marshmallow import Schema
from webargs import fields, validate

from gramps_webapi.api.dna import parse_raw_dna_match_string
from gramps_webapi.api.people_families_cache import CachePeopleFamiliesProxy
from gramps_webapi.types import Handle, MatchSegment, ResponseReturnValue

from ..blueprint import api_blueprint
from ..cache import request_cache_decorator
from ..util import get_db_handle, get_locale_for_language
from . import ProtectedResource
from .schemas import DnaMatchSchema, DnaSegmentSchema
from .util import get_object_or_none, get_person_profile_for_handle

SIDE_UNKNOWN = "U"
SIDE_MATERNAL = "M"
SIDE_PATERNAL = "P"


class DnaMatchesQueryArgs(Schema):
    """Query arguments for GET /people/<handle>/dna/matches."""

    locale = fields.Str(
        load_default=None,
        validate=validate.Length(min=2, max=5),
        metadata={
            "description": "Language code of the locale to use where applicable. Must be a valid code from the available translations."
        },
    )
    raw = fields.Bool(
        load_default=False,
        metadata={
            "description": "If true, include the raw segment data strings in the response."
        },
    )


class PersonDnaMatchesResource(ProtectedResource):
    """Resource for getting DNA match data for a person."""

    @api_blueprint.response(200, DnaMatchSchema(many=True))
    @api_blueprint.arguments(DnaMatchesQueryArgs, location="query")
    @request_cache_decorator
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
                if match_data is not None:
                    matches.append(match_data)
        return matches


class DnaMatchParserBodyArgs(Schema):
    """Body arguments for POST /dna/match-parser/."""

    string = fields.Str(
        required=True,
        metadata={"description": "The raw DNA match data string to parse."},
    )


class DnaMatchParserResource(ProtectedResource):
    """DNA match parser resource."""

    @api_blueprint.response(200, DnaSegmentSchema(many=True))
    @api_blueprint.arguments(DnaMatchParserBodyArgs, location="json")
    def post(self, args: dict) -> ResponseReturnValue:
        """Parse DNA match string."""
        return parse_raw_dna_match_string(args["string"])


def get_match_data(
    db_handle: DbReadBase,
    person: Person,
    association_index: int,
    locale: GrampsLocale = glocale,
    include_raw_data: bool = False,
) -> dict[str, Any] | None:
    """Get the DNA match data in the appropriate format.

    Return None if the associated person is missing or not available.
    """
    relationship = get_relationship_calculator(reinit=True, clocale=locale)
    association = person.get_person_ref_list()[association_index]
    associate = get_object_or_none(db_handle, "Person", association.ref)
    if associate is None:
        return None
    data, _ = relationship.get_relationship_distance_new(
        db_handle,
        person,
        associate,
        all_families=False,
        all_dist=True,
        only_birth=True,
    )
    loop_detected = isinstance(data, tuple)
    if loop_detected:
        # a relationship loop returns a single tuple even with all_dist=True
        data = [data]
    side = get_side(data)
    # a male's X chromosome always comes from his mother
    side_x = SIDE_MATERNAL if person.gender == Person.MALE else side

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
        note_segments = get_segments_from_note(
            db_handle, handle=note_handle, side=side, side_x=side_x
        )
        if note_segments:
            segments += note_segments
            note_handles_with_segments.append(note_handle)

    if loop_detected:
        # get_all_relationships fails on the same single tuple
        rel_strings, common_ancestors = [], []
    else:
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
            note: Note | None = get_object_or_none(db_handle, "Note", note_handle)
            if note is not None:
                raw_data.append(note.get())
        result["raw_data"] = raw_data
    return result


def get_side(data: list[tuple]) -> str:
    """Get the side of the shared DNA from the relationship paths.

    `data` is the list returned by `get_relationship_distance_new` with
    `all_dist=True`. The side is paternal or maternal only if every shortest
    path from the person to a common ancestor starts with the same parent.
    A path that starts with a sibling in a family without parents, or an empty
    path (the person is the common ancestor), gives an unknown side.
    """
    min_rank = min(row[0] for row in data)
    if min_rank <= 0:  # Unrelated
        return SIDE_UNKNOWN
    translate_sides = {"m": SIDE_MATERNAL, "f": SIDE_PATERNAL}
    sides = {translate_sides.get(row[2][:1]) for row in data if row[0] == min_rank}
    if len(sides) == 1:
        (only_side,) = sides
        if only_side is not None:
            return only_side
    return SIDE_UNKNOWN


def is_x_chromosome(chromosome: object) -> bool:
    """Return true if the chromosome label denotes the X chromosome."""
    label = str(chromosome).strip().upper().removeprefix("CHR")
    return label in {"X", "23"}


def get_segments_from_note(
    db_handle: DbReadBase,
    handle: Handle,
    side: str | None = None,
    side_x: str | None = None,
) -> list[MatchSegment]:
    """Get the segements from a note handle."""
    try:
        note: Note | None = db_handle.get_note_from_handle(handle)
    except HandleError:
        return []
    if note is None:
        return []
    raw_string: str = note.get()
    return parse_raw_match_string_with_default_side(
        raw_string, side=side, side_x=side_x
    )


def parse_raw_match_string_with_default_side(
    raw_string: str, side: str | None = None, side_x: str | None = None
) -> list[MatchSegment]:
    """Parse a raw DNA match string and return a list of segments.

    If the side is unknown, optionally set it to a default value. `side_x`
    is the default for the X chromosome; if it is None, `side` is used.
    """
    original_segments = parse_raw_dna_match_string(raw_string)
    if side_x is None:
        side_x = side
    segments = []
    for segment in original_segments:
        default = side_x if is_x_chromosome(segment["chromosome"]) else side
        if segment["side"] == SIDE_UNKNOWN and default is not None:
            segments.append(segment | {"side": default})
        else:
            segments.append(segment)
    return segments
