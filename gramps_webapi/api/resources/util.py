"""Gramps utility functions."""

from typing import List, Optional

from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.db.base import DbReadBase
from gramps.gen.display.name import NameDisplay
from gramps.gen.errors import HandleError
from gramps.gen.lib import Event, Person
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject

from gramps_webapi.types import GrampsId, Handle

nd = NameDisplay()
dd = GRAMPS_LOCALE.date_displayer


def get_event_date_from_handle(db: DbReadBase, handle: Handle) -> Optional[str]:
    """Return a formatted date for the event."""
    try:
        date = db.get_event_from_handle(handle).get_date_object()
    except AttributeError:
        return None
    return dd.display(date) or None


def get_event_place_from_handle(db: DbReadBase, handle: Handle) -> Optional[GrampsId]:
    """Get an event's place."""
    return get_event_place_grampsid(db, db.get_event_from_handle(handle))


def get_birthplace_grampsid(db: DbReadBase, person: Person) -> Optional[GrampsId]:
    """Return the name of a person's birth place."""
    birth_handle = person.get_birth_ref()
    try:
        return get_event_place_from_handle(db, birth_handle.ref)
    except (AttributeError, HandleError):
        return None


def get_deathplace_grampsid(db: DbReadBase, person: Person) -> Optional[GrampsId]:
    """Return the name of the death place."""
    death_ref = person.get_death_ref()
    try:
        return get_event_place_from_handle(db, death_ref.ref)
    except (AttributeError, HandleError):
        return None


def get_birthdate(db: DbReadBase, person: Person) -> Optional[str]:
    """Return the formatted birth date of a person."""
    birth_handle = person.get_birth_ref()
    try:
        return get_event_date_from_handle(db, birth_handle.ref)
    except (AttributeError, HandleError):
        return None


def get_deathdate(db: DbReadBase, person: Person) -> Optional[str]:
    """Return the formatted death date."""
    death_ref = person.get_death_ref()
    try:
        return get_event_date_from_handle(db, death_ref.ref)
    except (AttributeError, HandleError):
        return None


def get_event_place_grampsid(db: DbReadBase, event: Event) -> Optional[GrampsId]:
    """Get the event's place."""
    try:
        return db.get_place_from_handle(event.place).gramps_id
    except (HandleError, AttributeError):
        return None


def get_parents_grampsids(db: DbReadBase, person: Person) -> Optional[GrampsId]:
    """Get the Gramps IDs of the family's parents."""
    handle = person.get_main_parents_family_handle()
    try:
        return db.get_family_from_handle(handle).gramps_id
    except HandleError:
        return None


def get_families_grampsids(db: DbReadBase, person: Person) -> List[GrampsId]:
    """Get the Gramps IDs of all the person's families."""
    handles = person.get_family_handle_list() or []
    return [db.get_family_from_handle(handle).gramps_id for handle in handles]


def get_event_grampsids_roles(db, obj: GrampsObject):
    """Get the Gramps ID and role of events of a Gramps object."""
    return [
        {
            "gramps_id": db.get_event_from_handle(r.ref).gramps_id,
            "role": r.get_role().string,
        }
        for r in obj.get_event_ref_list()
    ]


def get_citation_grampsids(db: DbReadBase, obj: GrampsObject) -> List[GrampsId]:
    """Get the Gramps IDs of direct citations of a Gramps object."""
    return [
        db.get_citation_from_handle(handle).gramps_id
        for handle in obj.get_citation_list()
    ]


def get_note_grampsids(db: DbReadBase, obj: GrampsObject) -> List[GrampsId]:
    """Get the Gramps IDs of direct notes of a Gramps object."""
    return [db.get_note_from_handle(handle).gramps_id for handle in obj.get_note_list()]
