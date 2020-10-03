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


def get_surnames(surnames: List) -> List:
    """Get the attributes for the surnames."""
    return [
        {
            "connector": r.connector,
            "origintype": str(r.get_origintype()),
            "prefix": r.prefix,
            "primary": r.primary,
            "surname": r.surname
        }
        for r in surnames
    ]


def get_alternate_names(person: Person) -> List:
    """Get the alternate names for a Gramps Person."""
    return [
        {
            "call": r.call,
            "citations": r.get_citation_list(),
            "date": str(r.date),
            "display_as": r.display_as,
            "famnick": r.famnick,
            "first_name": r.first_name,
            "group_as": r.group_as,
            "nick": r.nick,
            "notes": r.get_note_list(),
            "private": r.private,
            "sort_as": r.sort_as,
            "surname_list": get_surnames(r.surname_list),
            "suffix": r.suffix,
            "title": r.title,
            "type": str(r.type)
        }
        for r in person.get_alternate_names()
    ]


def get_attributes(obj: GrampsObject) -> List:
    """Get the attributes for a Gramps object."""
    return [
        {
            "citations": r.get_citation_list(),
            "notes": r.get_note_list(),
            "private": r.private,
            "type": str(r.type),
            "value": r.value
        }
        for r in obj.get_attribute_list()
    ]

def get_event_references(obj: GrampsObject) -> List:
    """Get the event references for a Gramps object."""
    return [
        {
            "attributes": get_attributes(r),
            "notes": r.get_note_list(),
            "private": r.private,
            "reference": r.ref,
            "role": r.get_role().string
        }
        for r in obj.get_event_ref_list()
    ]


def get_media_references(obj: GrampsObject) -> List:
    """Get the media references for a Gramps object."""
    return [
        {
            "attributes": get_attributes(r),
            "citations": r.get_citation_list(),
            "notes": r.get_note_list(),
            "private": r.private,
            "rectangle": r.rect,
            "reference": r.ref
        }
        for r in obj.get_media_list()
    ]


def get_person_references(person: Person) -> List:
    """Get the person references, known as associations, for a Gramps Person."""
    return [
        {
            "citations": r.get_citation_list(),
            "notes": r.get_note_list(),
            "private": r.private,
            "reference": r.ref,
            "relationship": r.rel
        }
        for r in person.get_person_ref_list()
    ]


def get_urls(obj: GrampsObject) -> List:
    """Get the urls for a Gramps object."""
    return [
        {
            "description": r.desc,
            "path": r.path,
            "private": r.private,
            "type": str(r.type)
        }
        for r in obj.get_url_list()
    ]


def get_lds_events(obj: GrampsObject) -> List:
    """Get the lds ordination events for a Gramps object."""
    return [
        {
            "citations": r.get_citation_list(),
            "date": dd.display(r.date),
            "famc": r.famc,
            "notes": r.get_note_list(),
            "place": r.place,
            "private": r.private,
            "status": r.status,
            "temple": r.temple,
            "type": r.type,
        }
        for r in obj.get_lds_ord_list()
    ]
