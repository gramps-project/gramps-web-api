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

"""Render Gramps objects as text for the AI assistant.

Every referenced object is a Markdown link, so the model can cite it and look
it up with the matching tool.

Privacy is not handled here: when the user may not view private records, the
tools pass a private proxy database, which hides private objects (returning
None) and strips private parts from the objects it returns. The one exception
is backlinks, which the proxy does not filter by the privacy of the reference
itself, see `_backlinks`.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from gramps.gen.db.base import DbReadBase
from gramps.gen.errors import HandleError
from gramps.gen.lib import (
    ChildRefType,
    Citation,
    Event,
    EventRoleType,
    Family,
    Media,
    Name,
    Note,
    NoteType,
    Person,
    Place,
    Repository,
    Source,
)
from gramps.gen.utils.place import conv_lat_lon

from ..resources.util import display_date

MAX_BACKLINKS = 20
MAX_NOTES = 10
NOTE_PREVIEW_CHARS = 100

# GEDCOM attribute and event types that only carry import bookkeeping
SKIPPED_TYPES = {"RIN"}

GENDERS = {
    Person.FEMALE: "female",
    Person.MALE: "male",
    Person.UNKNOWN: "unknown",
    Person.OTHER: "other",
}


def _get(db_handle: DbReadBase, class_name: str, handle: str) -> Any:
    """Get an object by handle, or None if it is missing or private."""
    if not handle:
        return None
    try:
        return db_handle.method("get_%s_from_handle", class_name)(handle)
    except HandleError:
        return None


def _skipped(type_name: str) -> bool:
    """Whether an attribute or event type is import bookkeeping."""
    return type_name.startswith("_") or type_name in SKIPPED_TYPES


def _link(label: str, class_name: str, gramps_id: str) -> str:
    label = label.replace("[", "(").replace("]", ")").strip() or gramps_id
    return f"[{label}](/{class_name.lower()}/{gramps_id})"


def _date(obj) -> str:
    date = obj.get_date_object()
    if date is None or date.is_empty():
        return ""
    return display_date(date)


def _name(name: Name) -> str:
    parts = (name.first_name, name.get_surname(), name.suffix)
    return " ".join(part.strip() for part in parts if part.strip())


def _name_details(name: Name) -> str:
    """Searchable parts of a name that _name leaves out."""
    details = [
        (label, value.strip())
        for label, value in (
            ("title", name.get_title()),
            ("call name", name.get_call_name()),
            ("nickname", name.get_nick_name()),
            ("family nickname", name.get_family_nick_name()),
        )
    ]
    return ", ".join(f"{label} {value}" for label, value in details if value)


def _event_label(event: Event) -> str:
    return event.type.xml_str()


def _family_label(db_handle: DbReadBase, family: Family) -> str:
    parents = [
        _name(person.primary_name)
        for person in (
            _get(db_handle, "Person", family.father_handle),
            _get(db_handle, "Person", family.mother_handle),
        )
        if person is not None
    ]
    return " and ".join(parents) or family.gramps_id


def _place_name(place: Place) -> str:
    return place.get_name().get_value() or place.title or place.gramps_id


def _label(db_handle: DbReadBase, class_name: str, obj) -> str:
    """Return a short human-readable label for an object."""
    if class_name == "Person":
        return _name(obj.primary_name)
    if class_name == "Family":
        return _family_label(db_handle, obj)
    if class_name == "Event":
        date = _date(obj)
        return f"{_event_label(obj)}, {date}" if date else _event_label(obj)
    if class_name == "Place":
        return _place_name(obj)
    if class_name == "Source":
        return obj.title
    if class_name == "Citation":
        source = _get(db_handle, "Source", obj.source_handle)
        title = source.title if source else ""
        return ", ".join(part for part in (title, obj.page) if part)
    if class_name == "Repository":
        return obj.name
    if class_name == "Media":
        return obj.desc
    return obj.gramps_id


def _obj_link(db_handle: DbReadBase, class_name: str, obj) -> str:
    return _link(_label(db_handle, class_name, obj), class_name, obj.gramps_id)


def _person_line(db_handle: DbReadBase, person: Person) -> str:
    """A linked person name with life dates."""
    dates = []
    for prefix, ref in (
        ("born", person.get_birth_ref()),
        ("died", person.get_death_ref()),
    ):
        event = _get(db_handle, "Event", ref.ref) if ref else None
        date = _date(event) if event else ""
        if date:
            dates.append(f"{prefix} {date}")
    line = _obj_link(db_handle, "Person", person)
    if dates:
        line += f" ({', '.join(dates)})"
    return line


def _enclosing_places(db_handle: DbReadBase, place: Place) -> list[str]:
    """The names of the places enclosing a place, innermost first."""
    names = []
    seen = {place.handle}
    current = place
    while current.get_placeref_list():
        parent = _get(db_handle, "Place", current.get_placeref_list()[0].ref)
        if parent is None or parent.handle in seen:
            break
        seen.add(parent.handle)
        names.append(_place_name(parent))
        current = parent
    return names


def _place_hierarchy(db_handle: DbReadBase, place: Place) -> str:
    """The linked place followed by its enclosing places."""
    parts = [_obj_link(db_handle, "Place", place)]
    return ", ".join(parts + _enclosing_places(db_handle, place))


def _event_line(db_handle: DbReadBase, event: Event, role=None) -> str:
    """A linked event with date, place, description, and optional role."""
    line = _link(_event_label(event), "Event", event.gramps_id)
    details = []
    date = _date(event)
    if date:
        details.append(date)
    place = _get(db_handle, "Place", event.place)
    if place is not None:
        details.append(f"in {_place_hierarchy(db_handle, place)}")
    if details:
        line += ": " + " ".join(details)
    if event.description:
        line += f" ({event.description})"
    if role is not None and not role.is_primary() and not role.is_family():
        line += f" [role: {role.xml_str()}]"
    return line


def _event_lines(db_handle: DbReadBase, event_ref_list) -> list[str]:
    lines = []
    for event_ref in event_ref_list:
        event = _get(db_handle, "Event", event_ref.ref)
        if event is None or _skipped(event.type.xml_str()):
            continue
        lines.append("- " + _event_line(db_handle, event, event_ref.get_role()))
    return lines


def _section(title: str, lines: list[str]) -> list[str]:
    return [f"{title}:", *lines] if lines else []


def _attributes(obj) -> list[str]:
    attributes = [
        f"{attribute.get_type().xml_str()}: {attribute.get_value()}"
        for attribute in obj.get_attribute_list()
        if not _skipped(attribute.get_type().xml_str())
    ]
    return [f"Attributes: {'; '.join(attributes)}"] if attributes else []


def _addresses(obj) -> list[str]:
    lines = []
    for address in obj.get_address_list():
        parts = [
            address.get_street(),
            address.get_locality(),
            address.get_city(),
            address.get_county(),
            address.get_state(),
            address.get_postal_code(),
            address.get_country(),
        ]
        line = ", ".join(part for part in parts if part)
        if address.get_phone():
            line += f" (phone {address.get_phone()})"
        date = _date(address)
        if date:
            line += f" ({date})"
        if line:
            lines.append("- " + line)
    return _section("Addresses", lines)


def _urls(obj) -> list[str]:
    urls = [
        url.get_path()
        + (f" ({url.get_description()})" if url.get_description() else "")
        for url in obj.get_url_list()
    ]
    return [f"Web links: {'; '.join(urls)}"] if urls else []


def _tags(db_handle: DbReadBase, obj) -> list[str]:
    tags = []
    for handle in obj.get_tag_list():
        try:
            tags.append(db_handle.get_tag_from_handle(handle).get_name())
        except (HandleError, AttributeError):
            continue
    return [f"Tags: {', '.join(tags)}"] if tags else []


def _citations(db_handle: DbReadBase, obj) -> list[str]:
    links = [
        _obj_link(db_handle, "Citation", citation)
        for citation in (
            _get(db_handle, "Citation", handle) for handle in obj.get_citation_list()
        )
        if citation is not None
    ]
    return [f"Citations: {'; '.join(links)}"] if links else []


def _media(db_handle: DbReadBase, obj) -> list[str]:
    links = [
        _obj_link(db_handle, "Media", media)
        for media in (
            _get(db_handle, "Media", media_ref.ref)
            for media_ref in obj.get_media_list()
        )
        if media is not None
    ]
    return [f"Media: {'; '.join(links)}"] if links else []


def _note_text(note: Note) -> str:
    return re.sub(r"\s+", " ", note.get()).strip()


def _note_type(note: Note) -> str:
    if note.type.value in {NoteType.UNKNOWN, NoteType.GENERAL}:
        return ""
    return note.type.xml_str()


def _notes(db_handle: DbReadBase, obj) -> list[str]:
    """Note links with a short preview; get_note returns the full text."""
    lines = []
    notes = [_get(db_handle, "Note", handle) for handle in obj.get_note_list()]
    notes = [note for note in notes if note is not None]
    for note in notes[:MAX_NOTES]:
        text = _note_text(note)
        if len(text) > NOTE_PREVIEW_CHARS:
            text = text[:NOTE_PREVIEW_CHARS].rstrip() + "…"
        note_type = _note_type(note)
        line = "- " + _link(note.gramps_id, "Note", note.gramps_id)
        if note_type:
            line += f" ({note_type})"
        lines.append(f"{line}: {text}")
    if len(notes) > MAX_NOTES:
        lines.append(f"- … and {len(notes) - MAX_NOTES} more")
    return _section("Notes", lines)


def _backlinks(
    db_handle: DbReadBase,
    class_name: str,
    handle: str,
    include_classes: list[str] | None = None,
) -> list[tuple[str, Any]]:
    """Return the objects that reference an object.

    The private proxy's find_backlink_handles only hides private referencing
    objects, not private references (e.g. a private media reference of a
    public person). The proxy does strip those from the objects it returns,
    so a backlink is only kept if the returned object still references the
    target.
    """
    result = []
    for ref_class, ref_handle in db_handle.find_backlink_handles(
        handle, include_classes=include_classes
    ):
        obj = _get(db_handle, ref_class, ref_handle)
        if obj is None:
            continue
        if (class_name, handle) not in obj.get_referenced_handles_recursively():
            continue
        result.append((ref_class, obj))
    return result


def _referenced_by(db_handle: DbReadBase, class_name: str, obj) -> list[str]:
    backlinks = _backlinks(db_handle, class_name, obj.handle)
    links = [
        _obj_link(db_handle, ref_class, ref_obj)
        for ref_class, ref_obj in backlinks[:MAX_BACKLINKS]
    ]
    if len(backlinks) > MAX_BACKLINKS:
        links.append(f"… and {len(backlinks) - MAX_BACKLINKS} more")
    return [f"Referenced by: {'; '.join(links)}"] if links else []


# Primary objects


def _person(db_handle: DbReadBase, person: Person) -> list[str]:
    lines = [f"## Person: {_obj_link(db_handle, 'Person', person)}"]
    details = _name_details(person.get_primary_name())
    if details:
        lines.append(f"Name details: {details}")
    lines.append(f"Gender: {GENDERS.get(person.gender, 'unknown')}")
    alternate_names = [
        f"{_name(name)} ({', '.join(filter(None, [name.get_type().xml_str(), _name_details(name)]))})"
        for name in person.get_alternate_names()
    ]
    if alternate_names:
        lines.append(f"Also known as: {'; '.join(alternate_names)}")
    lines += _section("Events", _event_lines(db_handle, person.get_event_ref_list()))
    for family_handle in person.get_parent_family_handle_list():
        family = _get(db_handle, "Family", family_handle)
        child_refs = (
            [ref for ref in family.get_child_ref_list() if ref.ref == person.handle]
            if family is not None
            else []
        )
        if not child_refs:
            # the family does not list the person as a child
            continue
        parents = [
            _person_line(db_handle, parent)
            for parent in (
                _get(db_handle, "Person", family.father_handle),
                _get(db_handle, "Person", family.mother_handle),
            )
            if parent is not None
        ]
        child_ref = child_refs[0]
        line = f"Parents ({_link('family', 'Family', family.gramps_id)}): "
        line += " and ".join(parents) if parents else "unknown"
        if (
            child_ref.frel.value != ChildRefType.BIRTH
            or child_ref.mrel.value != ChildRefType.BIRTH
        ):
            line += (
                f" (relation to father: {child_ref.frel.xml_str()}, "
                f"relation to mother: {child_ref.mrel.xml_str()})"
            )
        lines.append(line)
    family_lines = []
    for family_handle in person.get_family_handle_list():
        family = _get(db_handle, "Family", family_handle)
        if family is None or person.handle not in (
            family.father_handle,
            family.mother_handle,
        ):
            # the family does not list the person as a parent
            continue
        spouse_handle = (
            family.mother_handle
            if family.father_handle == person.handle
            else family.father_handle
        )
        spouse = _get(db_handle, "Person", spouse_handle)
        line = f"- {_link('family', 'Family', family.gramps_id)}"
        line += f" with {_person_line(db_handle, spouse)}" if spouse else ""
        events = [
            _event_line(db_handle, event)
            for event in (
                _get(db_handle, "Event", event_ref.ref)
                for event_ref in family.get_event_ref_list()
            )
            if event is not None and not _skipped(event.type.xml_str())
        ]
        if events:
            line += "; " + "; ".join(events)
        children = [
            _person_line(db_handle, child)
            for child in (
                _get(db_handle, "Person", child_ref.ref)
                for child_ref in family.get_child_ref_list()
            )
            if child is not None
        ]
        if children:
            line += "; children: " + ", ".join(children)
        family_lines.append(line)
    lines += _section("Families", family_lines)
    associations = []
    for person_ref in person.get_person_ref_list():
        other = _get(db_handle, "Person", person_ref.ref)
        if other is not None:
            associations.append(f"{_person_line(db_handle, other)} ({person_ref.rel})")
    if associations:
        lines.append(f"Associations: {'; '.join(associations)}")
    lines += _attributes(person)
    lines += _addresses(person)
    lines += _urls(person)
    return lines


def _family(db_handle: DbReadBase, family: Family) -> list[str]:
    lines = [f"## Family: {_obj_link(db_handle, 'Family', family)}"]
    for title, handle in (
        ("Father", family.father_handle),
        ("Mother", family.mother_handle),
    ):
        parent = _get(db_handle, "Person", handle)
        if parent is not None:
            lines.append(f"{title}: {_person_line(db_handle, parent)}")
    if family.type:
        lines.append(f"Relationship: {family.type.xml_str()}")
    lines += _section("Events", _event_lines(db_handle, family.get_event_ref_list()))
    children = []
    for child_ref in family.get_child_ref_list():
        child = _get(db_handle, "Person", child_ref.ref)
        if child is None:
            continue
        line = "- " + _person_line(db_handle, child)
        if (
            child_ref.frel.value != ChildRefType.BIRTH
            or child_ref.mrel.value != ChildRefType.BIRTH
        ):
            line += (
                f" (relation to father: {child_ref.frel.xml_str()}, "
                f"relation to mother: {child_ref.mrel.xml_str()})"
            )
        children.append(line)
    lines += _section("Children", children)
    lines += _attributes(family)
    return lines


def _event(db_handle: DbReadBase, event: Event) -> list[str]:
    lines = [f"## Event: {_obj_link(db_handle, 'Event', event)}"]
    lines.append(f"Type: {event.type.xml_str()}")
    date = _date(event)
    if date:
        lines.append(f"Date: {date}")
    place = _get(db_handle, "Place", event.place)
    if place is not None:
        lines.append(f"Place: {_place_hierarchy(db_handle, place)}")
    if event.description:
        lines.append(f"Description: {event.description}")
    participants = []
    for ref_class, obj in _backlinks(
        db_handle, "Event", event.handle, include_classes=["Person", "Family"]
    ):
        for event_ref in obj.get_event_ref_list():
            if event_ref.ref != event.handle:
                continue
            role = event_ref.get_role()
            if ref_class == "Person":
                line = _person_line(db_handle, obj)
            else:
                line = _obj_link(db_handle, "Family", obj)
            if role.value != EventRoleType.PRIMARY:
                line += f" ({role.xml_str()})"
            participants.append("- " + line)
            break
    lines += _section("Participants", participants)
    lines += _attributes(event)
    return lines


def _place(db_handle: DbReadBase, place: Place) -> list[str]:
    lines = [f"## Place: {_obj_link(db_handle, 'Place', place)}"]
    if place.place_type:
        lines.append(f"Type: {place.place_type.xml_str()}")
    enclosing = _enclosing_places(db_handle, place)
    if enclosing:
        lines.append(f"Part of: {', '.join(enclosing)}")
    alt_names = [name.get_value() for name in place.get_alternative_names()]
    if alt_names:
        lines.append(f"Also known as: {'; '.join(alt_names)}")
    if place.code:
        lines.append(f"Code: {place.code}")
    latitude, longitude = conv_lat_lon(place.lat, place.long, format="D.D8")
    if latitude and longitude:
        lines.append(f"Coordinates: {float(latitude):.4f}, {float(longitude):.4f}")
    lines += _urls(place)
    return lines


def _citation(db_handle: DbReadBase, citation: Citation) -> list[str]:
    lines = [f"## Citation: {_obj_link(db_handle, 'Citation', citation)}"]
    source = _get(db_handle, "Source", citation.source_handle)
    if source is not None:
        lines.append(f"Source: {_obj_link(db_handle, 'Source', source)}")
    if citation.page.strip():
        lines.append(f"Page: {citation.page}")
    date = _date(citation)
    if date:
        lines.append(f"Date: {date}")
    lines += _attributes(citation)
    lines += _referenced_by(db_handle, "Citation", citation)
    return lines


def _source(db_handle: DbReadBase, source: Source) -> list[str]:
    lines = [f"## Source: {_obj_link(db_handle, 'Source', source)}"]
    if source.author:
        lines.append(f"Author: {source.author}")
    if source.pubinfo:
        lines.append(f"Publication info: {source.pubinfo}")
    if source.abbrev:
        lines.append(f"Abbreviation: {source.abbrev}")
    repositories = []
    for repo_ref in source.get_reporef_list():
        repository = _get(db_handle, "Repository", repo_ref.ref)
        if repository is None:
            continue
        line = _obj_link(db_handle, "Repository", repository)
        if repo_ref.call_number:
            line += f" (call number {repo_ref.call_number})"
        repositories.append(line)
    if repositories:
        lines.append(f"Repositories: {'; '.join(repositories)}")
    lines += _attributes(source)
    return lines


def _repository(db_handle: DbReadBase, repository: Repository) -> list[str]:
    lines = [f"## Repository: {_obj_link(db_handle, 'Repository', repository)}"]
    lines.append(f"Type: {repository.type.xml_str()}")
    lines += _addresses(repository)
    lines += _urls(repository)
    sources = _backlinks(
        db_handle, "Repository", repository.handle, include_classes=["Source"]
    )
    links = [_obj_link(db_handle, "Source", source) for _, source in sources]
    if len(links) > MAX_BACKLINKS:
        links = links[:MAX_BACKLINKS] + [f"… and {len(links) - MAX_BACKLINKS} more"]
    if links:
        lines.append(f"Sources: {'; '.join(links)}")
    return lines


def _note(db_handle: DbReadBase, note: Note) -> list[str]:
    lines = [f"## Note: {_link(note.gramps_id, 'Note', note.gramps_id)}"]
    note_type = _note_type(note)
    if note_type:
        lines.append(f"Type: {note_type}")
    lines += _referenced_by(db_handle, "Note", note)
    lines += ["Text:", re.sub(r"\n\s*\n+", "\n", note.get()).strip()]
    return lines


def _media_object(db_handle: DbReadBase, media: Media) -> list[str]:
    lines = [f"## Media: {_obj_link(db_handle, 'Media', media)}"]
    if media.mime:
        lines.append(f"Type: {media.mime}")
    date = _date(media)
    if date:
        lines.append(f"Date: {date}")
    if media.path:
        lines.append(f"File: {media.path}")
    lines += _attributes(media)
    lines += _referenced_by(db_handle, "Media", media)
    return lines


RENDERERS: dict[str, Callable[[DbReadBase, Any], list[str]]] = {
    "Person": _person,
    "Family": _family,
    "Event": _event,
    "Place": _place,
    "Citation": _citation,
    "Source": _source,
    "Repository": _repository,
    "Note": _note,
    "Media": _media_object,
}


def render_object(db_handle: DbReadBase, class_name: str, obj) -> str:
    """Render a Gramps object as Markdown text for the AI assistant."""
    lines = RENDERERS[class_name](db_handle, obj)
    if hasattr(obj, "get_citation_list"):
        lines += _citations(db_handle, obj)
    if hasattr(obj, "get_media_list"):
        lines += _media(db_handle, obj)
    if hasattr(obj, "get_note_list") and class_name != "Note":
        lines += _notes(db_handle, obj)
    lines += _tags(db_handle, obj)
    return "\n".join(lines)


def render_handle(db_handle: DbReadBase, class_name: str, handle: str) -> str:
    """Render the object with a handle.

    Empty if the object is missing or private, or of a class without a
    renderer (tags, which the search index contains as well).
    """
    if class_name not in RENDERERS:
        return ""
    obj = _get(db_handle, class_name, handle)
    if obj is None:
        return ""
    return render_object(db_handle, class_name, obj)
