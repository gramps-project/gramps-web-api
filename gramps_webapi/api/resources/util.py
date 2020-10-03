"""Gramps utility functions."""

from typing import List, Optional

from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.db.base import DbReadBase
from gramps.gen.display.name import NameDisplay
from gramps.gen.errors import HandleError
from gramps.gen.lib import Person
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject

from gramps_webapi.types import Handle

nd = NameDisplay()
dd = GRAMPS_LOCALE.date_displayer


def get_event_date_from_handle(db: DbReadBase, handle: Handle) -> Optional[str]:
    """Return a formatted date for the event."""
    try:
        date = db.get_event_from_handle(handle).get_date_object()
    except AttributeError:
        return None
    return dd.display(date) or None


def get_event_place_from_handle(db: DbReadBase, handle: Handle) -> Optional[Handle]:
    """Get the handle of an event's place."""
    try:
        return db.get_event_from_handle(handle).place
    except:
        return None


def get_birthplace_handle(db: DbReadBase, person: Person) -> Optional[Handle]:
    """Return the handle for a person's birth place."""
    birth_handle = person.get_birth_ref()
    try:
        return get_event_place_from_handle(db, birth_handle.ref)
    except (AttributeError, HandleError):
        return None


def get_deathplace_handle(db: DbReadBase, person: Person) -> Optional[Handle]:
    """Return the handle of the person's death place."""
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
