"""Gramps utility functions."""

from typing import Dict, List, Optional

from gramps.gen.const import GRAMPS_LOCALE
from gramps.gen.db.base import DbReadBase
from gramps.gen.display.name import NameDisplay
from gramps.gen.display.place import PlaceDisplay
from gramps.gen.errors import HandleError
from gramps.gen.lib import (Event, Family, Media, Person, Place, Repository,
                            Source)
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from gramps.gen.utils.db import (get_birth_or_fallback, get_death_or_fallback,
                                 get_divorce_or_fallback,
                                 get_marriage_or_fallback)
from gramps_webapi.types import Handle

nd = NameDisplay()
pd = PlaceDisplay()
dd = GRAMPS_LOCALE.date_displayer


def get_person_by_handle(db: DbReadBase, handle: Handle) -> Person:
    """Safe get person by handle."""
    try:
        return db.get_person_from_handle(handle)
    except HandleError:
        return None


def get_place_by_handle(db: DbReadBase, handle: Handle) -> Place:
    """Safe get place by handle."""
    try:
        return db.get_place_from_handle(handle)
    except HandleError:
        return None


def get_family_by_handle(db: DbReadBase, handle: Handle, extended=False) -> Family:
    """Get a family and all extended attributes."""
    try:
        obj = db.get_family_from_handle(handle)
    except HandleError:
        return None
    if extended:
        obj.extended = {
            "father": get_person_by_handle(db, obj.father_handle),
            "mother": get_person_by_handle(db, obj.mother_handle),
            "children": get_children_for_references(db, obj),
            "events": get_events_for_references(db, obj),
            "media": get_media_for_references(db, obj),
            "citations": [
                db.get_citation_from_handle(handle) for handle in obj.citation_list
            ],
            "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
            "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list],
        }
    return obj


def get_children_for_references(db: DbReadBase, family: Family) -> List[Person]:
    """Get children for a Family."""
    return [
        db.get_person_from_handle(child_ref.ref) for child_ref in family.child_ref_list
    ]


def get_events_for_references(db: DbReadBase, obj: GrampsObject) -> List[Event]:
    """Get events for a Gramps Object."""
    return [db.get_event_from_handle(event_ref.ref) for event_ref in obj.event_ref_list]


def get_media_for_references(db: DbReadBase, obj: GrampsObject) -> List[Media]:
    """Get media for a Gramps Object."""
    return [db.get_media_from_handle(media_ref.ref) for media_ref in obj.media_list]


def get_people_for_references(db: DbReadBase, person: Person) -> List[Person]:
    """Get people associated with a Person."""
    return [
        db.get_person_from_handle(person_ref.ref)
        for person_ref in person.person_ref_list
    ]


def get_repositories_for_references(db: DbReadBase, source: Source) -> List[Repository]:
    """Get repositories for a Source."""
    return [
        db.get_repository_from_handle(repo_ref.ref) for repo_ref in source.reporef_list
    ]


def get_source_by_handle(db: DbReadBase, handle: Handle) -> Source:
    """Get a source and all extended attributes."""
    obj = db.get_source_from_handle(handle)
    obj.extended = {
        "repositories": get_repositories_for_references(db, obj),
        "media": get_media_for_references(db, obj),
        "notes": [db.get_note_from_handle(handle) for handle in obj.note_list],
        "tags": [db.get_tag_from_handle(handle) for handle in obj.tag_list],
    }


def get_sex_profile(person: Person):
    """Get character substitution for enumerated sex."""
    if person.gender == person.MALE:
        return "M"
    if person.gender == person.FEMALE:
        return "F"
    return "U"


def get_event_profile_for_object(db: DbReadBase, event: Event) -> Dict:
    """Get event profile given an Event."""
    return {
        "type": str(event.type),
        "date": dd.display(event.date),
        "place": pd.display_event(db, event),
    }


def get_event_profile_for_handle(db: DbReadBase, handle: Handle) -> Dict:
    """Get event profile given a handle."""
    try:
        obj = db.get_event_from_handle(handle)
    except HandleError:
        return None
    return get_event_profile_for_object(db, obj)


def get_birth_profile(db: DbReadBase, person: Person) -> Dict:
    """Return best available birth information for a person."""
    event = get_birth_or_fallback(db, person)
    if event is None:
        return {}
    return get_event_profile_for_object(db, event)


def get_death_profile(db: DbReadBase, person: Person) -> Dict:
    """Return best available death information for a person."""
    event = get_death_or_fallback(db, person)
    if event is None:
        return {}
    return get_event_profile_for_object(db, event)


def get_marriage_profile(db: DbReadBase, family: Family) -> Dict:
    """Return best available marriage information for a couple."""
    event = get_marriage_or_fallback(db, family)
    if event is None:
        return {}
    return get_event_profile_for_object(db, event)


def get_divorce_profile(db: DbReadBase, family: Family) -> Dict:
    """Return best available divorce information for a couple."""
    event = get_divorce_or_fallback(db, family)
    if event is None:
        return {}
    return get_event_profile_for_object(db, event)


def get_person_profile_for_object(
    db: DbReadBase, person: Person, with_family=True, with_events=True
) -> Person:
    """Get person profile given a Person."""
    profile = {
        "handle": person.handle,
        "sex": get_sex_profile(person),
        "birth": get_birth_profile(db, person),
        "death": get_death_profile(db, person),
        "name_given": nd.display_given(person),
        "name_surname": person.primary_name.get_surname(),
    }
    if with_family:
        primary_parent_family_handle = person.get_main_parents_family_handle()
        profile["primary_parent_family"] = get_family_profile_for_handle(
            db, primary_parent_family_handle
        )
        profile["other_parent_families"] = []
        for handle in person.parent_family_list:
            if handle != primary_parent_family_handle:
                profile["other_parent_families"].append(
                    get_family_profile_for_handle(db, handle)
                )
        profile["families"] = [
            get_family_profile_for_handle(db, handle) for handle in person.family_list
        ]
    if with_events:
        profile["events"] = [
            get_event_profile_for_handle(db, event_ref.ref)
            for event_ref in person.event_ref_list
        ]
    return profile


def get_person_profile_for_handle(
    db: DbReadBase, handle: Handle, with_family=True, with_events=True
) -> Person:
    """Get person profile given a handle."""
    try:
        obj = db.get_person_from_handle(handle)
    except HandleError:
        return None
    return get_person_profile_for_object(db, obj, with_family, with_events)


def get_family_profile_for_object(
    db: DbReadBase, family: Family, with_events=True
) -> Family:
    """Get family profile given a Family."""
    profile = {
        "handle": family.handle,
        "father": get_person_profile_for_handle(
            db, family.father_handle, with_family=False, with_events=False
        ),
        "mother": get_person_profile_for_handle(
            db, family.mother_handle, with_family=False, with_events=False
        ),
        "relationship": family.type,
        "marriage": get_marriage_profile(db, family),
        "divorce": get_divorce_profile(db, family),
        "children": [
            get_person_profile_for_handle(
                db, child_ref.ref, with_family=False, with_events=False
            )
            for child_ref in family.child_ref_list
        ],
    }
    if with_events:
        profile["events"] = [
            get_event_profile_for_handle(db, event_ref.ref)
            for event_ref in family.event_ref_list
        ]
    return profile


def get_family_profile_for_handle(
    db: DbReadBase, handle: Handle, with_events=True
) -> Family:
    """Get family profile given a handle."""
    try:
        obj = db.get_family_from_handle(handle)
    except HandleError:
        return None
    return get_family_profile_for_object(db, obj, with_events)
