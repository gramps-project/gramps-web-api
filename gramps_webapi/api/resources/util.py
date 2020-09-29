"""Gramps utility functions."""

from typing import List, Optional

from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.db.base import DbReadBase
from gramps.gen.display.name import NameDisplay
from gramps.gen.errors import HandleError
from gramps.gen.lib import Event, Person, Family
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


def get_main_parents_grampsids(db: DbReadBase, person: Person) -> Optional[GrampsId]:
    """Get the Gramps IDs of the person's parents."""
    handle = person.get_main_parents_family_handle()
    try:
        return db.get_family_from_handle(handle).gramps_id
    except HandleError:
        return None


def get_parents_grampsids(db: DbReadBase, person: Person) -> List[GrampsId]:
    """Get the Gramps IDs of all the person's parents."""
    handles = person.get_parent_family_handle_list() or []
    return [db.get_family_from_handle(handle).gramps_id for handle in handles]


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


def get_attribute_references(db, obj: GrampsObject):
    """Get the attribute references for an object."""
    return [
        {
            "private": r.private,
            "type": str(r.type),
            "value": r.value,
            "citations": get_citation_grampsids(db, r),
            "notes": get_note_grampsids(db, r),
        }
        for r in obj.get_attribute_list()
    ]


def get_event_references(db, obj: GrampsObject):
    """Get the event references for an object."""
    return [
        {
            "gramps_id": db.get_event_from_handle(r.ref).gramps_id,
            "private": r.private,
            "role": r.get_role().string,
            "attributes": get_attribute_references(db, r),
            "notes": get_note_grampsids(db, r)
        }
        for r in obj.get_event_ref_list()
    ]


def get_media_references(db, obj: GrampsObject):
    """Get the media references for an object."""
    return [
        {
            "gramps_id": db.get_media_from_handle(r.ref).gramps_id,
            "private": r.private,
            "attributes": get_attribute_references(db, r),
            "citations": get_citation_grampsids(db, r),
            "notes": get_note_grampsids(db, r),
            "rect": r.rect
        }
        for r in obj.get_media_list()
    ]


def get_tag_list(db: DbReadBase, obj: GrampsObject) -> List[GrampsId]:
    """Get the Gramps IDs of the tags of a Gramps object."""
    tags = [db.get_tag_from_handle(handle) for handle in obj.get_tag_list()]
    return [
        {
            "name": tag.name,
            "color": tag.color,
            "priority": tag.priority,
            "change": tag.change
        }
        for tag in tags
    ]


def get_father_grampsid(db: DbReadBase, family: Family) -> GrampsId:
    """Get the Gramps ID of the father for a family."""
    handle = family.get_father_handle()
    try:
        return db.get_person_from_handle(handle).gramps_id
    except HandleError:
        return None


def get_mother_grampsid(db: DbReadBase, family: Family) -> GrampsId:
    """Get the Gramps ID of the mother for a family."""
    handle = family.get_mother_handle()
    try:
        return db.get_person_from_handle(handle).gramps_id
    except HandleError:
        return None


def get_children_grampsids(db: DbReadBase, family: Family):
    """Get the Gramps ID and role of children in a family."""
    return [
        {
            "gramps_id": db.get_person_from_handle(r.ref).gramps_id,
            "private": r.private,
            "mother_relation": r.get_mother_relation().string,
            "father_relation": r.get_father_relation().string,
            "citations": get_citation_grampsids(db, r),
            "notes": get_note_grampsids(db, r),
        }
        for r in family.get_child_ref_list()
    ]


def get_surname_list(surnames):
    """Get the attributes for a surname."""
    return [
        {
            "surname": r.surname,
            "prefix": r.prefix,
            "primary": r.primary,
            "origintype": "todo",
            "connector": r.connector
        }
        for r in surnames
    ]

def get_alternate_names(db, person: Person):
    """Get the attribute references for an object."""
    return [
        {
            "private": r.private,
            "date": str(r.date),
            "first_name": r.first_name,
            "surname_list": get_surname_list(r.surname_list),
            "suffix": r.suffix,
            "title": r.title,
            "call": r.call,
            "nick": r.nick,
            "famnick": r.famnick,
            "type": str(r.type),
            "group_as": r.group_as,
            "sort_as": r.sort_as,
            "display_as": r.display_as,
            "citations": get_citation_grampsids(db, r),
            "notes": get_note_grampsids(db, r),
        }
        for r in person.get_alternate_names()
    ]


def get_person_associations(db: DbReadBase, person: Person):
    """Get the associations for the person."""
    return [
        {
            "gramps_id": db.get_person_from_handle(r.ref).gramps_id,
            "private": r.private,
            "relation": r.rel,
            "citations": get_citation_grampsids(db, r),
            "notes": get_note_grampsids(db, r),
        }
        for r in person.get_person_ref_list()
    ]
