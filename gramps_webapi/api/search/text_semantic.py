"""Object to text conversion for semantic search."""

from __future__ import annotations

import re
from typing import Sequence

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
    NoteType,
    Media,
    ChildRef,
    ChildRefType,
)
from gramps.gen.utils.location import get_location_list
from gramps.gen.utils.place import conv_lat_lon

from ..resources.util import get_event_participants_for_handle


class PString:
    """String representation of an object with or without private strings.

    The class supports string addition with + or +=, but does not support
    inserting into f-strings.

    The `string_public` property contains the string that remains when all
    private information has been stripped. The `string_all` property contains
    the full string.

    If `private=True` is passed to the constructor, the string is assumed to
    be fully private. If `public_only=True` is passed, the string is assumed
    to only be present in the non-private case (this can be used e.g. for
    placeholders).

    To construct partially private strings, simply concatenate (add) several
    PStrings.

    Example:

    ```
    (
        PString("His father was ")
        + PString("Darth Vader.", private=True)
        + PString("a Jedi knight.", public_only=True)
    )
    ```
    """

    def __init__(
        self,
        string: str | PString = "",
        private: bool = False,
        public_only: bool = False,
    ):
        if isinstance(string, PString):
            self.string_public: str = "" if private else string.string_public
            self.string_all: str = "" if public_only else string.string_all
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

    def __repr__(self):
        """String representation."""
        return f"<PString(string_public={self.string_public})>"

    def __bool__(self) -> bool:
        return bool(self.string_all) or bool(self.string_public)


def pjoin(sep: str, pstrings: Sequence[PString | str]) -> PString:
    """Join a sequence of PStrings.

    Analogue of `string.join` for PStrings.
    """
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


def pwrap(
    before: str | PString, pstring: str | PString, after: str | PString
) -> PString:
    """Wrap a PString with a string before and after, if the string is not empty.

    Example:
    ```
    pwrap("(", PString("married", private=True), ")")
    ```
    will lead to "(married)" in the full string but an empty string (rather than "()")
    in the public case.
    """
    lhs = PString(before)
    rhs = PString(after)
    new = PString(pstring)
    if new.string_all:
        new.string_all = lhs.string_all + new.string_all + rhs.string_all
    if new.string_public:
        new.string_public = lhs.string_public + new.string_public + rhs.string_public
    return new


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


def tags_to_text(tag_list: Sequence[str], db_handle: DbReadBase) -> str:
    """Convert a tag list to text."""
    tags = []
    for tag_handle in tag_list:
        try:
            tag = db_handle.get_tag_from_handle(tag_handle)
            tags.append(tag.get_name())
        except HandleError:
            pass

    return ", ".join(tags)


def place_to_line(
    place: Place, db_handle: DbReadBase, include_hierarchy: bool = True
) -> str | PString:
    """Convert a place to a single line of text without participants."""
    place_hierarchy = get_location_list(db_handle, place)
    place_name = f"[{place_hierarchy[0][0]}](/place/{place.gramps_id})"
    if not include_hierarchy:
        return place_name
    # TODO while place refs cannot be private, there is the theoretical
    # possibility that a referenced parent place is private. This is
    # currently not accounted for.
    place_hierarchy[0] = place_name, ""
    return pjoin(", ", [name for name, _ in place_hierarchy])


def event_to_line(event: Event, db_handle: DbReadBase) -> PString:
    """Convert an event to a single line of text without participants."""
    event_type = event.type.xml_str()
    if event.date and not event.date.is_empty():
        date = date_to_text(event.date)
    else:
        date = ""
    string = PString(f"[{event_type}](/event/{event.gramps_id})")
    if date:
        string += f": {date}"
    if event.place:
        try:
            place = db_handle.get_place_from_handle(event.place)
            place_string = place_to_line(place, db_handle, include_hierarchy=False)
            string += PString(" in " + place_string, private=place.private)
        except HandleError:
            pass
    if event.description:
        if date or event.place:
            string += " - "
        string += f" {event.description}"
    return string


def child_ref_to_text(child_ref: ChildRef) -> str:
    """Convert a child reference to text."""
    frel = child_ref.frel.xml_str()
    mrel = child_ref.mrel.xml_str()
    return f"relation to father: {frel}, relation to mother: {mrel}"


def person_name_linked(person: Person) -> PString:
    """Format a person as a linked name."""
    person_name = PString(
        name_to_text(person.primary_name), private=person.primary_name.private
    )
    if person.primary_name.private:
        person_name = PString("N. N.", public_only=True)
    person_name = "[" + person_name + f"](/person/{person.gramps_id})"
    return person_name


def person_to_line(person: Person, db_handle: DbReadBase) -> PString:
    """Convert a person to a single line of text."""
    string = person_name_linked(person)
    try:
        if person.birth_ref_index < 0:
            raise IndexError  # negative index means event does not exist
        birth_ref = person.event_ref_list[person.birth_ref_index]
        birth = db_handle.get_event_from_handle(birth_ref.ref)
        if birth.date and not birth.date.is_empty():
            birth_date: str | PString = PString(
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
            death_date: str | PString = PString(
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


def get_family_title(obj: Family, db_handle: DbReadBase) -> PString:
    """Get a title for a family."""
    if obj.father_handle:
        person = db_handle.get_person_from_handle(obj.father_handle)
        private = person.private or person.primary_name.private
        father_name = PString(
            name_to_text(person.primary_name),
            private=private,
        )
        if private:
            father_name += PString("Unknown father", public_only=True)
    else:
        father_name = PString("Unknown father")
    if obj.mother_handle:
        person = db_handle.get_person_from_handle(obj.mother_handle)
        private = person.private or person.primary_name.private
        mother_name = PString(
            name_to_text(person.primary_name),
            private=private,
        )
        if private:
            mother_name += PString("unknown mother", public_only=True)
    else:
        mother_name = PString("unknown mother")
    return father_name + " and " + mother_name


# Primary objects
# TODO continue here


def person_to_text(obj: Person, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a person to text."""
    person_name = person_name_linked(obj)
    pronoun_poss = pronouns_poss[obj.gender]
    pronoun_pers = pronouns_pers[obj.gender]
    string = PString("## Person: " + person_name + "\n")
    string += (
        "This document contains information about the person " + person_name + ": "
        f"{pronoun_poss} name, life dates, and the events {pronoun_pers} participated "
        "in, such as birth, death, occupation, education, religious events, "
        "and others. "
    )
    if obj.alternate_names:
        for name in obj.alternate_names:
            name_type = name.type.xml_str()
            alt_name = (
                f"{pronoun_poss.capitalize()} {name_type} is {name_to_text(name)}. "
            )
            string += PString(alt_name, private=name.private)
    if obj.event_ref_list:
        event_strings: dict[str, list[PString]] = {}
        for event_ref in obj.event_ref_list:
            role = event_ref.role.xml_str()
            if role not in event_strings:
                event_strings[role] = []
            try:
                event = db_handle.get_event_from_handle(event_ref.ref)
            except HandleError:
                continue
            event_text = PString(
                event_to_line(event, db_handle),
                private=event_ref.private or event.private,
            )
            event_strings[role].append(event_text)
        if event_strings.get("Primary"):
            private = not any(
                pstring.string_public for pstring in event_strings["Primary"]
            )
            string += PString(
                private=private,
            )
            string += pwrap(
                person_name + " had the following personal events: ",
                pjoin("; ", event_strings["Primary"]),
                ". ",
            )
        other_roles = set(event_strings.keys()) - {"Primary"}
        if other_roles:
            other_role_string = PString()
            for role in other_roles:
                other_role_string += pwrap(
                    "",
                    pjoin(
                        "; ",
                        [
                            pwrap("", event_string, " (" + role + ")")
                            for event_string in event_strings[role]
                        ],
                    ),
                    ". ",
                )
            string += pwrap(
                person_name + " participated in the following events: ",
                other_role_string,
                " ",
            )
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
            " " + person_name + f" {rel_string} {name_ref}. ",
            private=person_ref.private,
        )
    if obj.tag_list:
        string += pwrap(
            person_name + " has the following tags in the database: ",
            tags_to_text(obj.tag_list, db_handle),
            ". ",
        )
    # not included:
    # media, address, attribute, URL, citation, note
    # eventref citations, notes, attributes
    if obj.private:
        return "", string.string_all
    return string.string_public, string.string_all


def family_to_text(obj: Family, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a family to text."""
    string = PString()
    name = get_family_title(obj, db_handle)
    name = "[" + name + f"](/family/{obj.gramps_id})"
    string += "## Family: " + name + "\n"
    string += "This document contains information about the family "
    string += name
    string += ": "
    string += (
        "The name and life dates of the parents, the names "
        "and life dates of all children, "
        "and the events the family participated in, such as marriage and residence. "
    )
    if obj.father_handle:
        try:
            person = db_handle.get_person_from_handle(obj.father_handle)
            father = person_to_line(person, db_handle)
            string += "The family's father was " + father + ". "
        except HandleError:
            pass
    if obj.mother_handle:
        try:
            person = db_handle.get_person_from_handle(obj.mother_handle)
            mother = person_to_line(person, db_handle)
            string += "The family's mother was " + mother + ". "
        except HandleError:
            pass
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
    # not included:
    # media, attribute, citation, note
    # childref citation, note, gender
    if obj.tag_list:
        string += pwrap(
            "The family has the following tags in the database: ",
            tags_to_text(obj.tag_list, db_handle),
            ". ",
        )
    if obj.private:
        return "", string.string_all
    return string.string_public, string.string_all


def event_to_text(obj: Event, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert an event to text."""
    title = obj.gramps_id
    name = PString("[" + title + f"](/event/{obj.gramps_id})")
    string = PString("## Event: " + name + "\n")
    string += "This document contains information about the event " + title + ", "
    string += "such as when and where it happened and who participated in it. "
    if obj.type:
        string += f"It was an event of type {obj.type.xml_str()}. "
    if obj.date and not obj.date.is_empty():
        string += f"It happened on the following date: {date_to_text(obj.date)}. "
    if obj.place:
        place = db_handle.get_place_from_handle(obj.place)
        place_string = place_to_line(place, db_handle)
        string += PString(
            "The event location was " + place_string + ". ", private=place.private
        )
    if obj.description:
        string += f'The event description is as follows: "{obj.description}". '
    participants = get_event_participants_for_handle(
        db_handle=db_handle, handle=obj.handle
    )
    roles: dict[str, list[PString]] = {}
    if participants.get("people"):
        for role, person in participants["people"]:
            role_str = role.xml_str()
            if role.xml_str() not in roles:
                roles[role_str] = []
            ref_private = all(
                [
                    event_ref.private
                    for event_ref in person.event_ref_list
                    if event_ref.ref == obj.handle
                ]
            )
            role_pstring = PString(
                f"[{name_to_text(person.primary_name)}](/person/{person.gramps_id})",
                private=person.private or ref_private,
            )
            roles[role_str].append(role_pstring)
    if roles.get("Primary"):
        string += pwrap(
            "The primary participant of the event was ",
            pjoin(", ", roles["Primary"]),
            ". ",
        )
    for k, v in roles.items():
        if k == "Primary":
            continue
        string += pwrap(
            f"The participants with role {k} of the event were ",
            pjoin(", ", v),
            ". ",
        )
    roles = {}
    if participants.get("families"):
        for role, family in participants["families"]:
            role_str = role.xml_str()
            if role_str not in roles:
                roles[role_str] = []
            ref_private = all(
                [
                    event_ref.private
                    for event_ref in family.event_ref_list
                    if event_ref.ref == obj.handle
                ]
            )
            family_title = get_family_title(family, db_handle)
            role_pstring = PString(
                "[" + family_title + f"](/family/{family.gramps_id})",
                private=family.private or ref_private,
            )

            roles[role_str].append(role_pstring)
    if roles.get("Family"):
        string += pwrap(
            "The primary participant family of the event was ",
            pjoin(", ", roles["Family"]),
            ". ",
        )
    # not included:
    # citation, media, note, attribute
    if obj.tag_list:
        string += pwrap(
            "The event has the following tags in the database: ",
            tags_to_text(obj.tag_list, db_handle),
            ". ",
        )
    if obj.private:
        return "", string.string_all
    return string.string_public, string.string_all


def place_to_text(obj: Place, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a place to text."""
    if obj.title and not obj.name:
        name = obj.title
    else:
        name = obj.get_name().value
    title = f"[{name}](/place/{obj.gramps_id})"
    string = PString(f"## Place: {title}\n")
    string += (
        f"This document contains data about the place {name}: "
        "its place type, geographic location, and enclosing places. "
    )
    if obj.place_type:
        string += f"{title} is a place of type {obj.place_type.xml_str()}. "
    if obj.alt_names:
        string += "It is also known as: "
        string += ", ".join([name.value for name in obj.alt_names])
        string += ". "
    if obj.code:
        string += f"Its place code is {obj.code}. "
    parent_list = get_location_list(db_handle, obj)
    latitude, longitude = conv_lat_lon(obj.lat, obj.long, format="D.D8")
    if latitude and longitude:
        string += (
            f"The greographical coordinates (latitude and longitude) of {title} "
            f"are {float(latitude):.4f}, {float(longitude):.4f}. "
        )
    if parent_list and len(parent_list) > 1:
        string += f"{title} is part of "
        string += pjoin(", ", [name for name, _ in parent_list[1:]])
        string += ". "
    # not included:
    # urls, media, citations, notes
    if obj.tag_list:
        string += pwrap(
            "The place " + title + " has the following tags in the database: ",
            tags_to_text(obj.tag_list, db_handle),
            ". ",
        )
    if obj.private:
        return "", string.string_all
    return string.string_public, string.string_all


def citation_to_text(obj: Citation, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a citation to text."""
    string = PString(f"## Citation: [{obj.gramps_id}](/citation/{obj.gramps_id})\n")
    string += (
        "This document contains the metadata of a citation, "
        "which is a reference to a source. "
    )
    if obj.source_handle:
        try:
            source = db_handle.get_source_from_handle(obj.source_handle)
            string += PString(
                "It cites the source "
                f"[{source.title or source.gramps_id}](/source/{source.gramps_id}). ",
                private=source.private,
            )
        except HandleError:
            pass
    if obj.page.strip():
        string += f"It cites page/volume: {obj.page}. "
    if obj.date and not obj.date.is_empty():
        string += f"The citation's date is {date_to_text(obj.date)}. "
    # not included:
    # note, media, attribute
    if obj.tag_list:
        string += pwrap(
            "The citation has the following tags in the database: ",
            tags_to_text(obj.tag_list, db_handle),
            ". ",
        )
    if obj.private:
        return "", string.string_all
    return string.string_public, string.string_all


def source_to_text(obj: Source, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a source to text."""
    title = f"[{obj.title or obj.gramps_id}](/source/{obj.gramps_id})"
    string = PString(f"## Source: {title}\n")
    if obj.author:
        string += f"The source's author was {obj.author}. "
    if obj.pubinfo:
        string += f"Source publication info: {obj.pubinfo}. "
    if obj.abbrev:
        string += f"The source is abbreviated as {obj.abbrev}. "
    # TODO reporef
    # notes, media, attributes
    if obj.tag_list:
        string += pwrap(
            "The source has the following tags in the database: ",
            tags_to_text(obj.tag_list, db_handle),
            ". ",
        )
    if obj.private:
        return "", string.string_all
    return string.string_public, string.string_all


def repository_to_text(obj: Repository, db_handle: DbReadBase) -> tuple[str, str]:
    title = f"[{obj.name}](/repository/{obj.gramps_id})"
    """Convert a repository to text."""
    string = PString(f"## Repository: {title}\n")
    string += f"{title} is a repository of type {obj.type.xml_str()}. "
    sources = []
    for _, source_handle in db_handle.find_backlink_handles(
        obj.handle, include_classes=["Source"]
    ):
        try:
            source = db_handle.get_source_from_handle(source_handle)
            ref_private = all(
                [
                    reporef.private
                    for reporef in source.reporef_list
                    if reporef.ref == obj.handle
                ]
            )
            sources.append(
                PString(
                    f"[{source.title}](/source/{source.gramps_id})",
                    private=source.private or ref_private,
                )
            )
        except HandleError:
            pass
    if sources:
        string += pwrap(
            f"The repository {title} contains the following sources: ",
            pjoin(", ", sources),
            ". ",
        )
    if obj.tag_list:
        string += pwrap(
            f"The repository {title} has the following tags in the database: ",
            tags_to_text(obj.tag_list, db_handle),
            ". ",
        )
    if obj.private:
        return "", string.string_all
    return string.string_public, string.string_all


def note_to_text(obj: Note, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a note to text."""
    string = PString(f"## Note [{obj.gramps_id}](/note/{obj.gramps_id})\n")
    string += (
        "This document contains the contents of the "
        f"[Note {obj.gramps_id}](/note/{obj.gramps_id}). "
    )
    if obj.type.value not in {NoteType.UNKNOWN, NoteType.GENERAL}:
        string += f"It is a note of type {obj.type.xml_str()}. "
    string += "Contents:\n"
    string += re.sub(r"\n+", "\n", obj.text.string)
    # not included: tags
    if obj.private:
        return "", string.string_all
    if obj.tag_list:
        string += pwrap(
            "The note has the following tags in the database: ",
            tags_to_text(obj.tag_list, db_handle),
            ". ",
        )
    return string.string_public, string.string_all


def media_to_text(obj: Media, db_handle: DbReadBase) -> tuple[str, str]:
    """Convert a media object to text."""
    name = f"[{obj.desc or obj.gramps_id}](/media/{obj.gramps_id})"
    string = PString(
        f"## Media object: {name}\n"
        "This document contains metadata about the media object "
        f"{name}. "
        f"Its media type is {obj.mime or 'unknown'}. "
    )
    if obj.desc:
        string += f"The media description is: {obj.desc}. "
    if obj.date and not obj.date.is_empty():
        string += f"The date of the media object is {date_to_text(obj.date)}. "
    if obj.path:
        string += f"The media object's path is {obj.path}. "
    # not included:
    # citations, attributes, notes, tags
    if obj.private:
        return "", string.string_all
    if obj.tag_list:
        string += pwrap(
            "The media object has the following tags in the database: ",
            tags_to_text(obj.tag_list, db_handle),
            ". ",
        )
    return string.string_public, string.string_all
