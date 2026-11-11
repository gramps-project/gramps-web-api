#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2026      David Straub
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

"""Pydantic AI tools that propose changes for the user to approve.

The tools never write to the database. Each one adds a change to the
proposal and dry-runs all changes proposed so far, so later changes can
build on earlier ones and errors are reported to the model right away.

The model describes changes in a format of its own, close to the rendered
records it reads: Gramps IDs instead of handles, dates as text, and
convenience fields such as a person's birth. Fields that are not given are
kept, list items are added, and nothing the format cannot express is lost.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from gramps.gen.datehandler import parser
from gramps.gen.db import DbTxn
from gramps.gen.db.base import DbWriteBase
from gramps.gen.lib import (
    ChildRef,
    Citation,
    Date,
    Event,
    EventRef,
    EventRoleType,
    EventType,
    Family,
    FamilyRelType,
    Note,
    NoteType,
    Person,
    Source,
    StyledText,
)
from gramps.gen.lib.grampstype import GrampsType
from gramps.gen.utils.id import create_id
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import RunContext

from ...types import TransactionJson
from ..dry_run import dry_run
from ..resources.delete import delete_object_in_transaction
from ..resources.util import add_object, update_object
from ..util import get_logger
from .deps import AgentDeps, Change
from .tools import log_tool_call

WRITE_PROPOSALS_PROMPT = """

You can propose changes to the database with the propose_change and propose_delete tools. Only propose changes when the user explicitly asks for a modification. Always look up the records involved before proposing a change, and if more than one record could be meant, ask the user which one instead of proposing anything. To cite a source, first add a citation (and the source, if it is not in the database), then reference the citation's Gramps ID. To change a record, send only the fields that change. If any part of the request can't be expressed with the fields of the tools, propose nothing and tell the user what you can't do; they can make that change in the app themselves. Never put information into a field it doesn't belong in. Proposed changes are not applied: the user reviews and approves them in the app, so never claim that a change has been made. After proposing, describe the changes in plain language."""

DATE_HELP = (
    "date in English, e.g. '3 May 1850', 'about 1842', 'before 1900' or "
    "'between 1840 and 1845'; empty string to clear"
)


class _Data(BaseModel):
    """Base of the format: fields it doesn't have are errors, not ignored."""

    model_config = ConfigDict(extra="forbid")


class Fact(_Data):
    """An event of a person or family, e.g. a birth or marriage."""

    date: str | None = Field(default=None, description=DATE_HELP)
    place: str | None = Field(
        default=None,
        description="Gramps ID of an existing place; empty string to clear",
    )
    description: str | None = None
    citations: list[str] | None = Field(
        default=None, description="Gramps IDs of citations to add"
    )


class OtherEvent(Fact):
    """An event of a type without a field of its own, e.g. an occupation."""

    event_type: str = Field(
        description="standard event type in English, e.g. 'Baptism', 'Burial', "
        "'Occupation', 'Residence'"
    )


class PersonData(_Data):
    """A person."""

    object_type: Literal["person"]
    given_name: str | None = None
    surname: str | None = None
    gender: Literal["male", "female", "unknown"] | None = Field(
        default=None,
        description="set it whenever the request implies it, e.g. 'son', "
        "'daughter', 'wife' or 'husband'",
    )
    birth: Fact | None = None
    death: Fact | None = None
    events: list[OtherEvent] | None = Field(
        default=None, description="other events to add"
    )
    citations: list[str] | None = Field(
        default=None, description="Gramps IDs of citations to add"
    )
    notes: list[str] | None = Field(
        default=None, description="Gramps IDs of notes to add"
    )


class FamilyData(_Data):
    """A family: a couple and their children."""

    object_type: Literal["family"]
    father: str | None = Field(default=None, description="Gramps ID of a person")
    mother: str | None = Field(default=None, description="Gramps ID of a person")
    children: list[str] | None = Field(
        default=None, description="Gramps IDs of children to add"
    )
    relationship: Literal["Married", "Unmarried", "Civil Union", "Unknown"] | None = (
        None
    )
    marriage: Fact | None = None
    events: list[OtherEvent] | None = Field(
        default=None, description="other events to add, e.g. 'Divorce'"
    )
    citations: list[str] | None = Field(
        default=None, description="Gramps IDs of citations to add"
    )
    notes: list[str] | None = Field(
        default=None, description="Gramps IDs of notes to add"
    )


class EventData(Fact):
    """An existing event. New events are added to a person or family."""

    object_type: Literal["event"]
    event_type: str | None = Field(
        default=None, description="standard event type in English"
    )
    notes: list[str] | None = Field(
        default=None, description="Gramps IDs of notes to add"
    )


class SourceData(_Data):
    """A source, e.g. a parish register or a book."""

    object_type: Literal["source"]
    title: str | None = Field(default=None, description="required for new sources")
    author: str | None = None
    publication_info: str | None = None
    notes: list[str] | None = Field(
        default=None, description="Gramps IDs of notes to add"
    )


class CitationData(_Data):
    """A citation: where in a source something was found."""

    object_type: Literal["citation"]
    source: str | None = Field(
        default=None,
        description="Gramps ID of the source; required for new citations",
    )
    page: str | None = Field(
        default=None, description="location within the source, e.g. 'p. 12'"
    )
    date: str | None = Field(default=None, description=DATE_HELP)
    confidence: Literal["very low", "low", "normal", "high", "very high"] | None = None
    notes: list[str] | None = Field(
        default=None, description="Gramps IDs of notes to add"
    )


class NoteData(_Data):
    """A note, e.g. a transcript or research notes."""

    object_type: Literal["note"]
    text: str | None = Field(default=None, description="required for new notes")
    note_type: str | None = Field(
        default=None,
        description="standard note type in English, e.g. 'General', "
        "'Research', 'Transcript'",
    )


ObjectData = Annotated[
    PersonData | FamilyData | EventData | SourceData | CitationData | NoteData,
    Field(discriminator="object_type"),
]

CONFIDENCE = {
    "very low": Citation.CONF_VERY_LOW,
    "low": Citation.CONF_LOW,
    "normal": Citation.CONF_NORMAL,
    "high": Citation.CONF_HIGH,
    "very high": Citation.CONF_VERY_HIGH,
}

GENDER = {
    "male": Person.MALE,
    "female": Person.FEMALE,
    "unknown": Person.UNKNOWN,
}


class ProposalError(ValueError):
    """A proposed change cannot be applied."""


def _get(db: DbWriteBase, class_name: str, gramps_id: str) -> Any:
    """Get an object by its Gramps ID, or fail."""
    obj = db.method("get_%s_from_gramps_id", class_name)(gramps_id)
    if obj is None:
        raise ProposalError(
            f"No {class_name.lower()} found with Gramps ID '{gramps_id}'."
        )
    return obj


def _handle(db: DbWriteBase, class_name: str, gramps_id: str) -> str:
    """Get the handle of an object by its Gramps ID; empty for no ID."""
    return _get(db, class_name, gramps_id).handle if gramps_id else ""


def _parse_date(text: str) -> Date:
    """Parse a date, or fail. An empty text gives an empty date."""
    date = parser.parse(text)
    if text and not date.is_valid():
        raise ProposalError(f"Cannot parse the date '{text}'. Use e.g. {DATE_HELP}.")
    return date


def _standard_type(type_class: type[GrampsType], name: str) -> GrampsType:
    """Get a standard Gramps type by its English name, or fail."""
    for xml_str in type_class().get_standard_xml():
        if xml_str.lower() == name.strip().lower():
            gramps_type = type_class()
            gramps_type.set_from_xml_str(xml_str)
            return gramps_type
    raise ProposalError(
        f"Unknown type '{name}'. Use one of: "
        + ", ".join(type_class().get_standard_xml())
    )


def _add_references(
    db: DbWriteBase, obj: Any, class_name: str, gramps_ids: list[str] | None
) -> None:
    """Add citations or notes to an object, unless it has them already."""
    for gramps_id in gramps_ids or []:
        handle = _handle(db, class_name, gramps_id)
        if class_name == "Citation":
            obj.add_citation(handle)
        else:
            obj.add_note(handle)


def _set_fact(db: DbWriteBase, event: Event, fact: Fact) -> None:
    """Set the fields of an event that are given."""
    if fact.date is not None:
        event.set_date_object(_parse_date(fact.date))
    if fact.place is not None:
        event.set_place_handle(_handle(db, "Place", fact.place))
    if fact.description is not None:
        event.set_description(fact.description)
    _add_references(db, event, "Citation", fact.citations)


def _add_event(
    db: DbWriteBase,
    trans: DbTxn,
    obj: Person | Family,
    event_type: EventType,
    fact: Fact,
) -> None:
    """Add a new event to a person (as primary) or family (as family)."""
    event = Event()
    event.set_handle(create_id())
    event.set_type(event_type)
    _set_fact(db, event, fact)
    add_object(db, event, trans)
    event_ref = EventRef()
    event_ref.set_reference_handle(event.handle)
    if isinstance(obj, Family):
        event_ref.set_role(EventRoleType(EventRoleType.FAMILY))
    obj.add_event_ref(event_ref)


def _set_event_of_type(
    db: DbWriteBase,
    trans: DbTxn,
    obj: Person | Family,
    event_type: int,
    fact: Fact,
) -> None:
    """Change the event of a type, e.g. the birth, or add it if there is none.

    For a person, the event is the one the birth or death index points to; for
    a family, the first one of the type in which the family has the family
    role.
    """
    event_ref = None
    if isinstance(obj, Person):
        event_ref = (
            obj.get_birth_ref()
            if event_type == EventType.BIRTH
            else obj.get_death_ref()
        )
    else:
        for ref in obj.get_event_ref_list():
            event = db.get_event_from_handle(ref.ref)
            if event.get_type() == event_type and ref.get_role().is_family():
                event_ref = ref
                break
    if event_ref is None:
        _add_event(db, trans, obj, EventType(event_type), fact)
        return
    event = db.get_event_from_handle(event_ref.ref)
    _set_fact(db, event, fact)
    update_object(db, event, trans)


def _set_events(
    db: DbWriteBase, trans: DbTxn, obj: Person | Family, events: list[OtherEvent]
) -> None:
    """Add other events to a person or family, unless they exist already."""
    fields = (
        {EventType.MARRIAGE: "marriage"}
        if isinstance(obj, Family)
        else {EventType.BIRTH: "birth", EventType.DEATH: "death"}
    )
    existing = [db.get_event_from_handle(ref.ref) for ref in obj.get_event_ref_list()]
    for other in events:
        event_type = _standard_type(EventType, other.event_type)
        if event_type.value in fields:
            raise ProposalError(
                f"Use the {fields[event_type.value]} field for a "
                f"{event_type.xml_str()} event, not events."
            )
        date = _parse_date(other.date or "")
        for event in existing:
            if (
                event.get_type() == event_type
                and event.get_date_object().is_equal(date)
                and event.get_description() == (other.description or "")
            ):
                raise ProposalError(
                    f"The {event_type.xml_str()} event {event.gramps_id} exists "
                    "already. Events are added, so only send new ones; change "
                    "existing events through their own Gramps ID."
                )
        _add_event(db, trans, obj, event_type, other)


def _apply_person(
    db: DbWriteBase, trans: DbTxn, person: Person, data: PersonData
) -> None:
    """Set the given fields of a person, without committing it."""
    name = person.get_primary_name()
    if data.given_name is not None:
        name.set_first_name(data.given_name)
    if data.surname is not None:
        name.get_primary_surname().set_surname(data.surname)
    if data.gender is not None:
        person.set_gender(GENDER[data.gender])
    if data.birth is not None:
        _set_event_of_type(db, trans, person, EventType.BIRTH, data.birth)
    if data.death is not None:
        _set_event_of_type(db, trans, person, EventType.DEATH, data.death)
    _set_events(db, trans, person, data.events or [])
    _add_references(db, person, "Citation", data.citations)
    _add_references(db, person, "Note", data.notes)
    # the indices of new birth or death events
    db.set_birth_death_index(person)


def _apply_family(
    db: DbWriteBase, trans: DbTxn, family: Family, data: FamilyData
) -> None:
    """Set the given fields of a family, without committing it."""
    if data.father is not None:
        family.set_father_handle(_handle(db, "Person", data.father) or None)
    if data.mother is not None:
        family.set_mother_handle(_handle(db, "Person", data.mother) or None)
    existing = {ref.ref for ref in family.get_child_ref_list()}
    for gramps_id in data.children or []:
        handle = _handle(db, "Person", gramps_id)
        if handle not in existing:
            child_ref = ChildRef()
            child_ref.set_reference_handle(handle)
            family.add_child_ref(child_ref)
    if data.relationship is not None:
        family.set_relationship(_standard_type(FamilyRelType, data.relationship))
    if data.marriage is not None:
        _set_event_of_type(db, trans, family, EventType.MARRIAGE, data.marriage)
    _set_events(db, trans, family, data.events or [])
    _add_references(db, family, "Citation", data.citations)
    _add_references(db, family, "Note", data.notes)


def _apply_event(db: DbWriteBase, event: Event, data: EventData) -> None:
    """Set the given fields of an event, without committing it."""
    if data.event_type is not None:
        event.set_type(_standard_type(EventType, data.event_type))
    _set_fact(db, event, data)
    _add_references(db, event, "Note", data.notes)


def _apply_source(db: DbWriteBase, source: Source, data: SourceData) -> None:
    """Set the given fields of a source, without committing it."""
    if data.title is not None:
        source.set_title(data.title)
    if data.author is not None:
        source.set_author(data.author)
    if data.publication_info is not None:
        source.set_publication_info(data.publication_info)
    _add_references(db, source, "Note", data.notes)


def _apply_citation(db: DbWriteBase, citation: Citation, data: CitationData) -> None:
    """Set the given fields of a citation, without committing it."""
    if data.source is not None:
        citation.set_reference_handle(_handle(db, "Source", data.source))
    if data.page is not None:
        citation.set_page(data.page)
    if data.date is not None:
        citation.set_date_object(_parse_date(data.date))
    if data.confidence is not None:
        citation.set_confidence_level(CONFIDENCE[data.confidence])
    _add_references(db, citation, "Note", data.notes)


def _apply_note(note: Note, data: NoteData) -> None:
    """Set the given fields of a note, without committing it."""
    if data.text is not None:
        note.set_styledtext(StyledText(data.text))
    if data.note_type is not None:
        note.set_type(_standard_type(NoteType, data.note_type))


NEW_OBJECTS = {
    "person": Person,
    "family": Family,
    "source": Source,
    "citation": Citation,
    "note": Note,
}


def _apply(db: DbWriteBase, trans: DbTxn, obj: Any, data: ObjectData) -> None:
    """Set the given fields of an object, without committing it."""
    if isinstance(data, PersonData):
        _apply_person(db, trans, obj, data)
    elif isinstance(data, FamilyData):
        _apply_family(db, trans, obj, data)
    elif isinstance(data, EventData):
        _apply_event(db, obj, data)
    elif isinstance(data, SourceData):
        _apply_source(db, obj, data)
    elif isinstance(data, CitationData):
        _apply_citation(db, obj, data)
    else:
        _apply_note(obj, data)


def _check_required(data: ObjectData) -> None:
    """Fail if a field required for new objects is missing."""
    if isinstance(data, SourceData) and not data.title:
        raise ProposalError("A new source needs a title.")
    if isinstance(data, CitationData) and not data.source:
        raise ProposalError("A new citation needs a source.")
    if isinstance(data, NoteData) and not data.text:
        raise ProposalError("A new note needs a text.")


def _effect(transaction: TransactionJson) -> list[tuple]:
    """What a transaction changes, apart from the last-changed timestamps."""

    def state(obj: dict[str, Any] | None) -> dict[str, Any] | None:
        return None if obj is None else {k: v for k, v in obj.items() if k != "change"}

    effect = []
    for item in transaction:
        old, new = state(item["old"]), state(item["new"])
        if item["type"] == "update" and old == new:
            continue
        effect.append((item["type"], item["_class"], item["handle"], new))
    return effect


def _propose(
    ctx: RunContext[AgentDeps], tool: str, change: Change, summary: str
) -> TransactionJson | str:
    """Add a change to the proposal if all changes so far can be applied.

    Returns the dry-run transaction, or an error message for the model.
    """
    proposal = ctx.deps.proposal
    if proposal is None:
        # the tools are only registered when proposals are allowed
        return "Proposing changes is not enabled."
    if ctx.deps.progress_callback:
        ctx.deps.progress_callback(tool, "Preparing changes...")
    changes = [*proposal.changes, change]

    def apply(db: DbWriteBase, trans: DbTxn) -> None:
        for each in changes:
            each(db, trans)

    try:
        transaction = dry_run(ctx.deps.tree, ctx.deps.user_id, apply)
    except ValueError as exc:
        # includes ProposalError and errors of add_object/update_object
        return f"Nothing was proposed: {exc}"
    except Exception:  # pylint: disable=broad-except
        get_logger().exception("Error while preparing a proposal in %s", tool)
        return "Nothing was proposed: an unexpected error occurred."
    if _effect(transaction) == _effect(proposal.transaction):
        return "Nothing was proposed: this would not change anything."
    proposal.changes = changes
    proposal.summaries.append(summary)
    proposal.transaction = transaction
    return transaction


def _describe(data: ObjectData) -> str:
    """The given fields of the data, for the summary."""
    fields = data.model_dump(exclude_none=True, exclude={"object_type"})
    return json.dumps(fields, ensure_ascii=False)


def _add(ctx: RunContext[AgentDeps], data: ObjectData) -> str:
    """Propose adding a new object."""
    if isinstance(data, EventData):
        return (
            "Nothing was proposed: add events through the person or family "
            "they belong to."
        )
    try:
        _check_required(data)
    except ProposalError as exc:
        return f"Nothing was proposed: {exc}"
    handle = create_id()

    def change(db: DbWriteBase, trans: DbTxn) -> None:
        obj = NEW_OBJECTS[data.object_type]()
        obj.set_handle(handle)
        _apply(db, trans, obj, data)
        add_object(db, obj, trans)

    result = _propose(
        ctx, "propose_change", change, f"Add {data.object_type}: {_describe(data)}"
    )
    if isinstance(result, str):
        return result
    gramps_id = next(
        item["new"]["gramps_id"] for item in result if item["handle"] == handle
    )
    return f"Proposed (not applied yet): add {data.object_type} {gramps_id}."


def _update(ctx: RunContext[AgentDeps], data: ObjectData, gramps_id: str) -> str:
    """Propose changing an existing object."""
    if not data.model_dump(exclude_none=True, exclude={"object_type"}):
        return "Nothing was proposed: no field to change was given."
    class_name = data.object_type.capitalize()

    def change(db: DbWriteBase, trans: DbTxn) -> None:
        obj = _get(db, class_name, gramps_id)
        _apply(db, trans, obj, data)
        update_object(db, obj, trans)

    summary = f"Change {data.object_type} {gramps_id}: {_describe(data)}"
    result = _propose(ctx, "propose_change", change, summary)
    if isinstance(result, str):
        return result
    return f"Proposed (not applied yet): change {data.object_type} {gramps_id}."


@log_tool_call
def propose_change(
    ctx: RunContext[AgentDeps], data: ObjectData, gramps_id: str = ""
) -> str:
    """Propose adding a new record, or changing an existing one.

    Nothing is written: the user reviews and approves the change in the app.
    Without a Gramps ID, a new person, family, source, citation or note is
    added; events are added through the person or family they belong to
    (birth, death, marriage or events). With a Gramps ID, the existing person,
    family, event, source, citation or note is changed: only the fields given
    are changed, and list items are added to the existing ones. For a
    person's birth or death, or a family's marriage, the existing event is
    changed, or a new one is added if there is none. A changed event changes
    for everyone who shares it. References to other records use their Gramps
    IDs, including records added by earlier proposals.

    Args:
        data: The fields of the new record, or the fields to change
        gramps_id: Gramps ID of the record to change (e.g., "I0044"); empty
            to add a new record

    Returns:
        What was proposed, including a new record's Gramps ID, or why nothing
        was proposed.
    """
    if gramps_id:
        return _update(ctx, data, gramps_id)
    return _add(ctx, data)


@log_tool_call
def propose_delete(
    ctx: RunContext[AgentDeps],
    object_type: Literal["person", "family", "event", "source", "citation", "note"],
    gramps_id: str,
) -> str:
    """Propose deleting a person, family, event, source, citation or note.

    Nothing is written: the user reviews and approves the change in the app.
    References to the object are removed from other records. Only propose
    this if the user explicitly asked to delete this record.

    Args:
        object_type: Type of the object to delete
        gramps_id: Gramps ID of the object (e.g., "E0123")

    Returns:
        What was proposed, or why nothing was proposed.
    """
    class_name = object_type.capitalize()

    def change(db: DbWriteBase, trans: DbTxn) -> None:
        obj = _get(db, class_name, gramps_id)
        delete_object_in_transaction(db, obj.handle, class_name, trans)

    summary = f"Delete {object_type} {gramps_id}"
    result = _propose(ctx, "propose_delete", change, summary)
    if isinstance(result, str):
        return result
    return f"Proposed (not applied yet): delete {object_type} {gramps_id}."
