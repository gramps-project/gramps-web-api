"""Object to text conversion for semantic search."""

from __future__ import annotations
import re

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
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


# Utility functions


class PString:
    """String representation of an object with or without private strings."""

    def __init__(
        self, string: str = "", private: bool = False, public_only: bool = False
    ):
        if isinstance(string, PString):
            self.string_public = "" if private else string.string_public
            self.string_all = "" if public_only else string.string_all
        else:
            if not isinstance(string, str):
                raise ValueError(f"Not a string: {string}")
            self.string_public = "" if private else string
            self.string_all = "" if public_only else string

    def __add__(self, other):
        """Add two object strings."""
        rhs = other if isinstance(other, PString) else PString(other)
        result = PString()
        result.string_public = self.string_public + rhs.string_public
        result.string_all = self.string_all + rhs.string_all
        return result

    def __radd__(self, other):
        """Add two object strings."""
        rhs = other if isinstance(other, PString) else PString(other)
        return rhs + self

    def __iadd__(self, other):
        """Add an object string to self."""
        rhs = other if isinstance(other, PString) else PString(other)
        self.string_public += rhs.string_public
        self.string_all += rhs.string_all
        return self

    def __str__(self):
        """String representation."""
        return f"<PString(string_public={self.string_public})>"

    def __bool__(self) -> bool:
        return bool(self.string_all) or bool(self.string_public)


def pjoin(sep: str, pstrings: list[PString | str]) -> PString:
    string = PString()
    pstrings_cast = [
        pstring if isinstance(pstring, PString) else PString(pstring)
        for pstring in pstrings
    ]
    string.string_all = sep.join(
        [pstring.string_all for pstring in pstrings_cast if pstring.string_all]
    )
    string.string_public = sep.join(
        [pstring.string_public for pstring in pstrings_cast if pstring.string_public]
    )
    return string


def pwrap(before: str, pstring: PString, after: str) -> PString:
    """Wrap a PString with a string before and after, if the string is not empty."""
    new = PString(pstring)
    if new.string_all:
        new.string_all = before + new.string_all + after
    if new.string_public:
        new.string_public = before + new.string_public + after
    return new


def join_sentence(words: list[str | PString], sep: str = ",") -> PString:
    """Join strings with a seperator, "and" before the last element, and a full stop."""
    if isinstance(words, str):
        raise ValueError("words should be a list of strings")
    if not words:
        return ""
    if len(words) == 1:
        return words[0]
    if len(words) == 2:
        return pjoin(" and ", words)
    return pjoin(f"{sep} ", words[:-1]) + f"{sep} and " + words[-1] + "."


# Secondary objects


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
    return pjoin(", ", [name for name, _ in place_hierarchy])


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
        try:
            place = db_handle.get_place_from_handle(event.place)
            place_string = place_to_line(place, db_handle, include_hierarchy=False)
            string += PString(f" in {place_string}", private=place.private)
        except HandleError:
            pass
    if event.description:
        if date or event.place:
            string += " - "
        string += f" {event.description}"
    return string


def child_ref_to_text(child_ref: ChildRef) -> str:
    frel = child_ref.frel.xml_str()
    mrel = child_ref.mrel.xml_str()
    return f"relation to father: {frel}, relation to mother: {mrel}"


def person_to_line(person: Person, db_handle: DbReadBase) -> PString:
    string = PString(
        f"[{name_to_text(person.primary_name)}](/person/{person.gramps_id})"
    )
    try:
        if person.birth_ref_index < 0:
            raise IndexError  # negative index means event does not exist
        birth_ref = person.event_ref_list[person.birth_ref_index]
        birth = db_handle.get_event_from_handle(birth_ref.ref)
        if birth.date and not birth.date.is_empty():
            birth_date = PString(
                date_to_text(birth.date), private=birth.private or birth_ref.private
            )
        else:
            birth_date = ""
    except (IndexError, HandleError):
        birth_date = ""
    try:
        if person.death_ref_index < 0:
            raise IndexError  # negative index means event does not exist
        death_ref = person.event_ref_list[person.death_ref_index]
        death = db_handle.get_event_from_handle(death_ref.ref)
        if death.date and not death.date.is_empty():
            death_date = PString(
                date_to_text(death.date), private=death.private or death_ref.private
            )
        else:
            death_date = ""
    except (IndexError, HandleError):
        death_date = ""
    birth_date = pwrap("born ", birth_date, "")
    death_date = pwrap("died ", death_date, "")
    life_dates = pjoin(", ", [birth_date, death_date])
    if life_dates:
        string += pwrap(" (", life_dates, ")")
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

# Primary objects


def person_to_text(obj: Person, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a person to text."""
    name = f"[{name_to_text(obj.primary_name)}](/person/{obj.gramps_id})"
    # FIXME primary name could be private
    pronoun_poss = pronouns_poss[obj.gender]
    pronoun_pers = pronouns_pers[obj.gender]
    string = PString(f"## Person: {name}\n")
    string += (
        f"This document contains information about the person {name}: "
        f"{pronoun_poss} name, life dates, and the events {pronoun_pers} participated in, "
        "such as birth, death, occupation, education, religious events, and others. "
    )
    if obj.alternate_names:
        for name in obj.alternate_names:
            name_type = name.type.xml_str()
            alt_name = (
                f"{pronoun_poss.capitalize()} {name_type} is {name_to_text(name)}. "
            )
            string += PString(alt_name, private=name.private)
    # FIXME
    # if obj.event_ref_list:
    #     event_strings = {}
    #     event_strings_public = {}
    #     for event_ref in obj.event_ref_list:
    #         role = event_ref.role.xml_str()
    #         if role not in event_strings:
    #             event_strings[role] = []
    #         if role not in event_strings_public:
    #             event_strings_public[role] = []
    #         try:
    #             event = db_handle.get_event_from_handle(event_ref.ref)
    #         except HandleError:
    #             continue
    #         event_text = event_to_line(event, db_handle)
    #         event_strings[role].append(event_text)
    #         if not event_ref.private and not event.private:
    #             event_strings_public[role].append(event_text)
    #     if event_strings.get("Primary"):
    #         string += f" {name} had the following personal events: "
    #         string += pjoin("; ", event_strings["Primary"]) + "."
    #     if event_strings_public.get("Primary"):
    #         string += f" {name} had the following personal events: "
    #         string += pjoin("; ", event_strings_public["Primary"]) + "."
    #     other_roles = set(event_strings.keys()) - {"Primary"}
    #     if other_roles:
    #         string += f" {name} participated in the following events: "
    #         for role in other_roles:
    #             string += (
    #                 pjoin("; ",
    #                     [
    #                         f"{event_string} ({role})"
    #                         for event_string in event_strings[role]
    #                     ]
    #                 )
    #                 + "."
    #             )
    #     other_roles = set(event_strings_public.keys()) - {"Primary"}
    #     if other_roles:
    #         string_public += f" {name} participated in the following events: "
    #         for role in other_roles:
    #             string_public += (
    #                 pjoin("; ",
    #                     [
    #                         f"{event_string} ({role})"
    #                         for event_string in event_strings_public[role]
    #                     ]
    #                 )
    #                 + "."
    #             )
    for person_ref in obj.person_ref_list:
        if person_ref.rel == "DNA":
            rel_string = "has a DNA match with"
        else:
            rel_string = f"has an association of type {person_ref.rel} with"
        try:
            ref_person = db_handle.get_person_from_handle(person_ref.ref)
        except HandleError:
            continue
        name_ref = (
            f"[{name_to_text(ref_person.primary_name)}]"
            f"(/person/{ref_person.gramps_id})"
        )
        string += PString(
            f" {name} {rel_string} {name_ref}.", private=person_ref.private
        )
    # media, address, attribute, URL, citation, note, tags
    # eventref citations, notes, attributes
    if obj.private:
        return "", string.string_all
    return string.string_public, string.string_all


def family_to_text(obj: Family, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a family to text."""
    string = PString()
    if obj.father_handle:
        person = db_handle.get_person_from_handle(obj.father_handle)
        father = person_to_line(person, db_handle)
        father_name = name_to_text(person.primary_name)
    if obj.mother_handle:
        person = db_handle.get_person_from_handle(obj.mother_handle)
        mother = person_to_line(person, db_handle)
        mother_name = name_to_text(person.primary_name)
    if obj.father_handle and obj.mother_handle:
        name = father_name + " and " + mother_name
    elif obj.father_handle:
        name = father_name + " and unknown mother"
    elif obj.mother_handle:
        name = mother_name + " and unknown father"
    else:
        name = "Family with unknown parents"
    name = "[" + name + f"](/family/{obj.gramps_id})"
    string += "## Family: " + name + "\n"
    string += "This document contains information about the family "
    string += name
    string += ": "
    string += (
        "The name and life dates of the parents, the names and life dates of all children, "
        "and the events the family participated in, such as marriage and residence. "
    )
    if obj.father_handle:
        string += "The family's father was " + father + ". "
    if obj.mother_handle:
        string += "The family's mother was " + mother + ". "
    if obj.type:
        string += f"Their relationship was: {obj.type.xml_str()}. "
    if obj.event_ref_list:
        string += name + " had the following family events: "
        event_strings = []
        for event_ref in obj.event_ref_list:
            event = db_handle.get_event_from_handle(event_ref.ref)
            event_text = event_to_line(event, db_handle)
            event_strings.append(event_text)
        string += pjoin(";", event_strings) + ". "
    if obj.child_ref_list:
        string += PString(
            name + " had the following children: ",
            private=all([child_ref.private for child_ref in obj.child_ref_list]),
        )
        child_strings = []
        for child_ref in obj.child_ref_list:
            try:
                person = db_handle.get_person_from_handle(child_ref.ref)
            except HandleError:
                continue
            string_child = PString(
                person_to_line(person, db_handle),
                private=child_ref.private or person.private,
            )
            if (
                child_ref.frel.value != ChildRefType.BIRTH
                or child_ref.mrel.value != ChildRefType.BIRTH
            ):
                string_child += PString(
                    " (" + child_ref_to_text(child_ref) + ")",
                    private=child_ref.private or person.private or child_ref.private,
                )
            if string_child:
                child_strings.append(string_child)
        string += pjoin(", ", child_strings)
    # TODO media, attribute, citation, note, tags
    # childref citation, note, gender
    if obj.private:
        return "", string.string_all
    return string.string_public, string.string_all


def event_to_text(obj: Event, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert an event to text."""
    string = PString(
        f"""Type: event
Gramps ID: {obj.gramps_id}
"""
    )
    if obj.type:
        string += f"Event type: {obj.type.xml_str()}\n"
    if obj.date and not obj.date.is_empty():
        string += f"Event date: {date_to_text(obj.date)}\n"
    if obj.place:
        place = db_handle.get_place_from_handle(obj.place)
        place_string = place_to_line(place, db_handle)
        string += "Event location: " + place_string + "\n"
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
        return "", string.string_all
    return string.string_public, string.string_all


def place_to_text(obj: Place, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a place to text."""
    string = PString(
        f"""Type: place
Gramps ID: {obj.gramps_id}
"""
    )
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
        string += pjoin(", ", [name for name, _ in parent_list[1:]])
        string += "\n"
    # TODO urls, media, citations, notes, tags
    if obj.private:
        return "", string.string_all
    return string.string_public, string.string_all


def citation_to_text(obj: Citation, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a citation to text."""
    string = PString(
        f"""Type: citation
Gramps ID: {obj.gramps_id}
"""
    )
    if obj.date and not obj.date.is_empty():
        string += f"Date: {date_to_text(obj.date)}\n"
    if obj.page:
        string += f"Page/Volume: {obj.page}\n"
    # TODO source
    # note, media, attribute, tags
    if obj.private:
        return "", string.string_all
    return string.string_public, string.string_all


def source_to_text(obj: Source, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a source to text."""
    string = PString(
        f"""Type: source
Gramps ID: {obj.gramps_id}
"""
    )
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
        return "", string.string_all
    return string.string_public, string.string_all


def repository_to_text(obj: Repository, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a repository to text."""
    string = PString(
        f"""Type: repository
Gramps ID: {obj.gramps_id}
Repository type: {obj.type.xml_str()}
Repository name: {obj.name}
"""
    )
    # TODO: sources
    # URLs, address, tags
    if obj.private:
        return "", string.string_all
    return string.string_public, string.string_all


def note_to_text(obj: Note, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a note to text."""
    note_text = re.sub(r"\n+", "\n", obj.text.string)
    string = PString(
        f"""Type: note
Gramps ID: {obj.gramps_id}
Note text:
{note_text}
"""
    )
    # TODO: referencing objects?
    # tags
    if obj.private:
        return "", string.string_all
    return string.string_public, string.string_all


def media_to_text(obj: Media, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a media object to text."""
    string = PString(
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
        return "", string.string_all
    return string.string_public, string.string_all
