"""Gramps utility functions."""

from typing import List, Optional

from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.db.base import DbReadBase
from gramps.gen.display.name import NameDisplay
from gramps.gen.errors import HandleError
from gramps.gen.lib import Event, Family, Media, Person, Repository, Source
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
        return (
            db.get_place_from_handle(db.get_event_from_handle(handle).place)
            .get_name()
            .get_value()
        )
    except:
        return None


def get_birthplace(db: DbReadBase, person: Person) -> Optional[Handle]:
    """Return the handle for a person's birth place."""
    birth_handle = person.get_birth_ref()
    try:
        return get_event_place_from_handle(db, birth_handle.ref)
    except (AttributeError, HandleError):
        return None


def get_deathplace(db: DbReadBase, person: Person) -> Optional[Handle]:
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


def get_person_by_handle(db: DbReadBase, handle: Handle) -> Person:
    """Safe get person by handle."""
    try:
        return db.get_person_from_handle(handle)
    except HandleError:
        return None


def get_children(db: DbReadBase, family: Family) -> List[Person]:
    """Get children for a Family."""
    return [
        db.get_person_from_handle(child_ref.ref) for child_ref in family.child_ref_list
    ]


def get_events(db: DbReadBase, obj: GrampsObject) -> List[Event]:
    """Get events for a Gramps Object."""
    return [db.get_event_from_handle(event_ref.ref) for event_ref in obj.event_ref_list]


def get_media(db: DbReadBase, obj: GrampsObject) -> List[Media]:
    """Get media for a Gramps Object."""
    return [db.get_media_from_handle(media_ref.ref) for media_ref in obj.media_list]


def get_people(db: DbReadBase, person: Person) -> List[Person]:
    """Get people associated with a Person."""
    return [
        db.get_person_from_handle(person_ref.ref)
        for person_ref in person.person_ref_list
    ]


def get_family(db: DbReadBase, handle: Handle) -> Family:
    """Get a family and all extended attributes."""
    try:
        obj = db.get_family_from_handle(handle)
    except HandleError:
        return None
    obj.extended = {
        "father": get_person_by_handle(db, obj.father_handle),
        "mother": get_person_by_handle(db, obj.mother_handle),
        "children": get_children(db, obj),
        "events": get_events(db, obj),
        "media": get_media(db, obj),
        "citations": [
            db.get_citation_from_handle(handle) for handle in obj.citation_list
        ],
        "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
        "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list],
    }
    return obj


def get_repositories(db: DbReadBase, source: Source) -> List[Repository]:
    """Get repositories for a Source."""
    return [
        db.get_repository_from_handle(repo_ref.ref) for repo_ref in source.reporef_list
    ]


def get_source(db: DbReadBase, handle: Handle) -> Source:
    """Get a source and all extended attributes."""
    obj = db.get_source_from_handle(handle)
    obj.extended = {
        "repositories": get_repositories(db, obj),
        "media": get_media(db, obj),
        "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
        "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list],
    }
