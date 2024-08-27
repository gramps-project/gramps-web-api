"""Object to text conversion for semantic search."""

from __future__ import annotations

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db.base import DbReadBase
from gramps.gen.lib import (
    Event,
    Date,
    Family,
    Person,
    Place,
    Citation,
    Source,
    Repository,
    Name,
    Note,
    Media,
    ChildRef,
    ChildRefType,
)
from gramps.gen.utils.location import get_location_list
from gramps.gen.utils.place import conv_lat_lon

from ..resources.util import get_event_participants_for_handle

# things that can be private:
# Address, Attribute, ChildRef, EventRef, MediaRef, Name, PersonRef, RepoRef, SrcAttribute, URL
# Citation, Event, Family, Media, Note, Person, Place, Repository, Source

# TODO general: citation, media (p), note, attribute (p), tags, URLs


def join_sentence(words: list[str], sep: str = ","):
    """Join strings with a seperator, "and" before the last element, and a full stop."""
    if isinstance(words, str):
        raise ValueError("words should be a list of strings")
    if not words:
        return ""
    if len(words) == 1:
        return words[0]
    if len(words) == 2:
        return " and ".join(words)
    return f"{sep} ".join(words[:-1]) + f"{sep} and {words[-1]}."


def date_to_text(date: Date) -> str:
    """Convert a date to text."""
    return glocale.date_displayer.display(date)


def name_to_text(name: Name) -> str:
    """Convert a name to a text."""
    given = name.first_name
    surname = name.get_surname()
    suffix = name.suffix
    return f"{given} {surname} {suffix}".strip()


def place_to_line(
    place: Place, db_handle: DbReadBase, include_hierarchy: bool = True
) -> str:
    """Convert a place to a single line of text without participants."""
    place_hierarchy = get_location_list(db_handle, place)
    place_name = f"[{place_hierarchy[0][0]}](/place/{place.gramps_id})"
    if not include_hierarchy:
        return place_name
    place_hierarchy[0] = place_name, ""
    return ", ".join(name for name, _ in place_hierarchy)


def event_to_line(event: Event, db_handle: DbReadBase) -> str:
    """Convert an event to a single line of text without participants."""
    event_type = event.type.xml_str()
    if event.date and not event.date.is_empty():
        date = date_to_text(event.date)
    else:
        date = ""
    string = f"[{event_type}](/event/{event.gramps_id})"
    if date:
        string += f": {date}"
    if event.place:
        place = db_handle.get_place_from_handle(event.place)
        place_string = place_to_line(place, db_handle, include_hierarchy=False)
        string += f" in {place_string}"
    if event.description:
        if date or event.place:
            string += " - "
        string += f" {event.description}"
    return string


def child_ref_to_text(child_ref: ChildRef) -> str:
    frel = child_ref.frel.xml_str()
    mrel = child_ref.mrel.xml_str()
    return f"relation to father: {frel}, relation to mother: {mrel}"


def person_to_line(person: Person, db_handle: DbReadBase) -> str:
    string = f"[{name_to_text(person.primary_name)}](/person/{person.gramps_id})"
    try:
        if person.birth_ref_index < 0:
            raise IndexError  # negative index means event does not exist
        birth_ref = person.event_ref_list[person.birth_ref_index]
        birth = db_handle.get_event_from_handle(birth_ref.ref)
        if birth.date and not birth.date.is_empty():
            birth_date = date_to_text(birth.date)
        else:
            birth_date = ""
    except IndexError:
        birth_date = ""
    try:
        if person.death_ref_index < 0:
            raise IndexError  # negative index means event does not exist
        death_ref = person.event_ref_list[person.death_ref_index]
        death = db_handle.get_event_from_handle(death_ref.ref)
        if death.date and not death.date.is_empty():
            death_date = date_to_text(death.date)
        else:
            death_date = ""
    except IndexError:
        death_date = ""
    if birth_date or death_date:
        string += " ("
    if birth_date:
        string += f"born {birth_date}"
    if birth_date and death_date:
        string += ", "
    if death_date:
        string += f"died {death_date}"
    if birth_date or death_date:
        string += ")"
    return string


genders = {
    Person.FEMALE: "female",
    Person.MALE: "male",
    Person.UNKNOWN: "unknown",
    Person.OTHER: "other",
}


pronouns_poss = {
    Person.FEMALE: "her",
    Person.MALE: "his",
    Person.UNKNOWN: "their",
    Person.OTHER: "their",
}

pronouns_pers = {
    Person.FEMALE: "she",
    Person.MALE: "he",
    Person.UNKNOWN: "they",
    Person.OTHER: "they",
}


def person_to_text(obj: Person, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a person to text."""
    name = f"[{name_to_text(obj.primary_name)}](/person/{obj.gramps_id})"
    pronoun_poss = pronouns_poss[obj.gender]
    pronoun_pers = pronouns_pers[obj.gender]
    string = f"## Person: {name}\n"
    string += (
        f"This document contains information about the person {name}: "
        f"{pronoun_poss} name, life dates, and the events {pronoun_pers} participated in, "
        "such as birth, death, occupation, education, religious events, and others. "
    )
    if obj.alternate_names:
        for name in obj.alternate_names:
            name_type = name.type.xml_str()
            string += (
                f"{pronoun_poss.capitalize()} {name_type} is {name_to_text(name)}."
            )
    if obj.event_ref_list:
        event_strings = {}
        for event_ref in obj.event_ref_list:
            role = event_ref.role.xml_str()
            if role not in event_strings:
                event_strings[role] = []
            event = db_handle.get_event_from_handle(event_ref.ref)
            event_text = event_to_line(event, db_handle)
            event_strings[role].append(event_text)
        if event_strings.get("Primary"):
            string += f" {name} had the following personal events: "
            string += "; ".join(event_strings["Primary"]) + "."
        other_roles = set(event_strings.keys()) - {"Primary"}
        if other_roles:
            string += f" {name} participated in the following events: "
            for role in other_roles:
                string += (
                    "; ".join(
                        [
                            f"{event_string} ({role})"
                            for event_string in event_strings[role]
                        ]
                    )
                    + "."
                )
    # TODO personref
    # private names!
    # media, address, attribute, URL, citation, note, tags
    # eventref citations, notes, attributes
    if obj.private:
        return "", string
    return string, string


def family_to_text(obj: Family, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a family to text."""
    if obj.father_handle:
        person = db_handle.get_person_from_handle(obj.father_handle)
        father = person_to_line(person, db_handle)
        father_name = name_to_text(person.primary_name)
    if obj.mother_handle:
        person = db_handle.get_person_from_handle(obj.mother_handle)
        mother = person_to_line(person, db_handle)
        mother_name = name_to_text(person.primary_name)
    if obj.father_handle and obj.mother_handle:
        name = f"{father_name} and {mother_name}"
    elif obj.father_handle:
        name = f"{father_name} and unknown mother"
    elif obj.mother_handle:
        name = f"{mother_name} and unknown father"
    else:
        name = "Family with unknown parents"
    name = f"[{name}](/family/{obj.gramps_id})"
    string = f"## Family: {name}\n"
    string += (
        f"This document contains information about the family {name}: "
        f"The name and life dates of the parents, the names and life dates of all children, "
        "and the events the family participated in, such as marriage and residence. "
    )
    if obj.father_handle:
        string += f"The family's father was {father}. "
    if obj.mother_handle:
        string += f"The family's mother was {mother}. "
    if obj.type:
        string += f"Their relationship was: {obj.type.xml_str()}. "
    if obj.event_ref_list:
        string += f"{name} had the following family events: "
        event_strings = []
        for event_ref in obj.event_ref_list:
            event = db_handle.get_event_from_handle(event_ref.ref)
            event_text = event_to_line(event, db_handle)
            event_strings.append(event_text)
        string += "; ".join(event_strings) + ". "
    string_public = string
    if obj.child_ref_list:
        string += f"{name} had the following children: "
        if not all([child_ref.private for child_ref in obj.child_ref_list]):
            string_public += f"{name} had the following children: "
        child_strings = []
        child_strings_public = []
        for child_ref in obj.child_ref_list:
            person = db_handle.get_person_from_handle(child_ref.ref)
            string_child = f"{person_to_line(person, db_handle)}"
            if (
                child_ref.frel.value != ChildRefType.BIRTH
                or child_ref.mrel.value != ChildRefType.BIRTH
            ):
                string_child += f" ({child_ref_to_text(child_ref)})"
            child_strings.append(string_child)
            if not child_ref.private:
                child_strings_public.append(string_child)
        string += join_sentence(child_strings)
        string_public += join_sentence(child_strings_public)
    # TODO media, attribute, citation, note, tags
    # childref citation, note, gender
    if obj.private:
        return "", string
    return string_public, string


def event_to_text(obj: Event, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert an event to text."""
    string = f"""Type: event
Gramps ID: {obj.gramps_id}
"""
    if obj.type:
        string += f"Event type: {obj.type.xml_str()}\n"
    if obj.date and not obj.date.is_empty():
        string += f"Event date: {date_to_text(obj.date)}\n"
    if obj.place:
        place = db_handle.get_place_from_handle(obj.place)
        place_string = place_to_line(place, db_handle)
        string += f"Event location: {place_string}\n"
    if obj.description:
        string += f"Event description: {obj.description}\n"
    participants = get_event_participants_for_handle(
        db_handle=db_handle, handle=obj.handle
    )
    if participants.get("people"):
        for role, person in participants["people"]:
            string += (
                f"Participant ({role.xml_str()}): "
                f"{name_to_text(person.primary_name)} "
                f"(Gramps ID: {person.gramps_id})\n"
            )
    if participants.get("families"):
        for role, family in participants["families"]:
            string += f"Participant family ({role.xml_str()}): {family.gramps_id}\n"
    # TODO citation, media, note, attribute, tags
    if obj.private:
        return "", string
    return string, string


def place_to_text(obj: Place, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a place to text."""
    string = f"""Type: place
Gramps ID: {obj.gramps_id}
"""
    if obj.title and not obj.name:
        string += f"Place title: {obj.title}\n"
    else:
        string += f"Place name: {obj.get_name().value}\n"
    if obj.alt_names:
        for name in obj.alt_names:
            f"Also known as: {name.value}"
    if obj.place_type:
        string += f"Place type: {obj.place_type.xml_str()}\n"
    if obj.code:
        string += f"Place code: {obj.code}\n"
    parent_list = get_location_list(db_handle, obj)
    latitude, longitude = conv_lat_lon(obj.lat, obj.long, format="D.D8")
    if latitude and longitude:
        string += (
            f"Latitude: {float(latitude):.5f}, Longitude: {float(longitude):.5f}\n"
        )
    if parent_list and len(parent_list) > 1:
        string += "Part of: "
        string += ", ".join(name for name, _ in parent_list[1:])
        string += "\n"
    # TODO urls, media, citations, notes, tags
    if obj.private:
        return "", string
    return string, string


def citation_to_text(obj: Citation, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a citation to text."""
    string = f"""Type: citation
Gramps ID: {obj.gramps_id}
"""
    if obj.date and not obj.date.is_empty():
        string += f"Date: {date_to_text(obj.date)}\n"
    if obj.page:
        string += f"Page/Volume: {obj.page}\n"
    # TODO source
    # note, media, attribute, tags
    if obj.private:
        return "", string
    return string, string


def source_to_text(obj: Source, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a source to text."""
    string = f"""Type: source
Gramps ID: {obj.gramps_id}
"""
    if obj.title:
        string += f"Source title: {obj.title}\n"
    if obj.author:
        string += f"Source author: {obj.author}\n"
    if obj.pubinfo:
        string += f"Source publication info: {obj.pubinfo}\n"
    if obj.abbrev:
        string += f"Source abbrevation: {obj.abbrev}\n"
    # TODO reporef
    # notes, media, attributes, tags
    if obj.private:
        return "", string
    return string, string


def repository_to_text(obj: Repository, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a repository to text."""
    string = f"""Type: repository
Gramps ID: {obj.gramps_id}
Repository type: {obj.type.xml_str()}
Repository name: {obj.name}
"""
    if obj.private:
        string_public = ""
    else:
        string_public = string
    # TODO: sources
    # URLs, address, tags
    return string_public, string


def note_to_text(obj: Note, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a note to text."""
    string = f"""Type: note
Gramps ID: {obj.gramps_id}
Note text:
{obj.text.string}
"""
    # TODO: referencing objects?
    # tags
    if obj.private:
        return "", string
    return string, string


def media_to_text(obj: Media, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a media object to text."""
    string = (
        "This document contains metadata about the media object "
        f"[{obj.gramps_id}](/media/{obj.gramps_id}). "
        f"Its media type is {obj.mime or 'unknown'}. "
    )
    if obj.desc:
        f"The media description is: {obj.desc}. "
    if obj.date and not obj.date.is_empty():
        string += f"Media date: {date_to_text(obj.date)}. "
    # TODO: referencing objects?
    # citations, attributes, notes, tags
    if obj.private:
        return "", string
    return string, string
