#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2000-2007  Donald N. Allingham
# Copyright (C) 2009       Brian G. Matherly
# Copyright (C) 2009       Gary Burton
# Copyright (C) 2009       Benny Malengier
# Copyright (C) 2011       Tim G L Lyons
# Copyright (C) 2010,2011,2014  Nick Hall
# Copyright (C) 2021       David Straub
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#


"""Functions for deleting objects with references."""

from typing import Any, Callable, Dict, List, Optional

from gramps.gen.db import DbTxn, DbWriteBase
from gramps.gen.utils.db import (
    get_citation_referents,
    get_media_referents,
    get_note_referents,
    get_source_and_citation_referents,
)

from ...const import GRAMPS_OBJECT_PLURAL
from ..util import get_total_number_of_objects
from .util import transaction_to_json


def delete_person(db_handle: DbWriteBase, handle: str, trans: DbTxn) -> None:
    """Delete an person and its references."""
    person = db_handle.get_person_from_handle(handle)
    db_handle.delete_person_from_database(person, trans)


def delete_family(db_handle: DbWriteBase, handle: str, trans: DbTxn) -> None:
    """Delete a family and its references."""
    return db_handle.remove_family_relationships(handle, trans=trans)


def delete_event(db_handle: DbWriteBase, handle: str, trans: DbTxn) -> None:
    """Delete an event and its references."""
    ev_handle_list = [handle]
    person_list = [
        item[1] for item in db_handle.find_backlink_handles(handle, ["Person"])
    ]
    family_list = [
        item[1] for item in db_handle.find_backlink_handles(handle, ["Family"])
    ]

    for person_handle in person_list:
        person = db_handle.get_person_from_handle(person_handle)
        person.remove_handle_references("Event", ev_handle_list)
        db_handle.commit_person(person, trans)

    for family_handle in family_list:
        family = db_handle.get_family_from_handle(family_handle)
        family.remove_handle_references("Event", ev_handle_list)
        db_handle.commit_family(family, trans)

    db_handle.remove_event(handle, trans)


def delete_citation(db_handle: DbWriteBase, handle: str, trans: DbTxn) -> None:
    """Delete an event and its references."""
    (
        person_list,
        family_list,
        event_list,
        place_list,
        source_list,
        media_list,
        repo_list,
    ) = get_citation_referents(handle, db_handle)

    citation = db_handle.get_citation_from_handle(handle)
    ctn_handle_list = [handle]

    for _handle in person_list:
        person = db_handle.get_person_from_handle(_handle)
        person.remove_citation_references(ctn_handle_list)
        db_handle.commit_person(person, trans)

    for _handle in family_list:
        family = db_handle.get_family_from_handle(_handle)
        family.remove_citation_references(ctn_handle_list)
        db_handle.commit_family(family, trans)

    for _handle in event_list:
        event = db_handle.get_event_from_handle(_handle)
        event.remove_citation_references(ctn_handle_list)
        db_handle.commit_event(event, trans)

    for _handle in place_list:
        place = db_handle.get_place_from_handle(_handle)
        place.remove_citation_references(ctn_handle_list)
        db_handle.commit_place(place, trans)

    for _handle in source_list:
        source = db_handle.get_source_from_handle(_handle)
        source.remove_citation_references(ctn_handle_list)
        db_handle.commit_source(source, trans)

    for _handle in media_list:
        media = db_handle.get_media_from_handle(_handle)
        media.remove_citation_references(ctn_handle_list)
        db_handle.commit_media(media, trans)

    for _handle in repo_list:
        repo = db_handle.get_repository_from_handle(_handle)
        repo.remove_citation_references(ctn_handle_list)
        db_handle.commit_repository(repo, trans)

    db_handle.remove_citation(citation.get_handle(), trans)


def delete_media(db_handle: DbWriteBase, handle: str, trans: DbTxn) -> None:
    """Delete an media object and its references."""
    (
        person_list,
        family_list,
        event_list,
        place_list,
        source_list,
        citation_list,
    ) = get_media_referents(handle, db_handle)

    for _handle in person_list:
        person = db_handle.get_person_from_handle(_handle)
        new_list = [
            photo
            for photo in person.get_media_list()
            if photo.get_reference_handle() != handle
        ]
        person.set_media_list(new_list)
        db_handle.commit_person(person, trans)

    for _handle in family_list:
        family = db_handle.get_family_from_handle(_handle)
        new_list = [
            photo
            for photo in family.get_media_list()
            if photo.get_reference_handle() != handle
        ]
        family.set_media_list(new_list)
        db_handle.commit_family(family, trans)

    for _handle in event_list:
        event = db_handle.get_event_from_handle(_handle)
        new_list = [
            photo
            for photo in event.get_media_list()
            if photo.get_reference_handle() != handle
        ]
        event.set_media_list(new_list)
        db_handle.commit_event(event, trans)

    for _handle in place_list:
        place = db_handle.get_place_from_handle(_handle)
        new_list = [
            photo
            for photo in place.get_media_list()
            if photo.get_reference_handle() != handle
        ]
        place.set_media_list(new_list)
        db_handle.commit_place(place, trans)

    for _handle in source_list:
        source = db_handle.get_source_from_handle(_handle)
        new_list = [
            photo
            for photo in source.get_media_list()
            if photo.get_reference_handle() != handle
        ]
        source.set_media_list(new_list)
        db_handle.commit_source(source, trans)

    for _handle in citation_list:
        citation = db_handle.get_citation_from_handle(_handle)
        new_list = [
            photo
            for photo in citation.get_media_list()
            if photo.get_reference_handle() != handle
        ]
        citation.set_media_list(new_list)
        db_handle.commit_citation(citation, trans)

    db_handle.remove_media(handle, trans)


def delete_note(db_handle: DbWriteBase, handle: str, trans: DbTxn) -> None:
    """Delete a note and its references."""
    note = db_handle.get_note_from_handle(handle)
    (
        person_list,
        family_list,
        event_list,
        place_list,
        source_list,
        citation_list,
        media_list,
        repo_list,
    ) = get_note_referents(handle, db_handle)

    note_handle = note.get_handle()

    for _handle in person_list:
        person = db_handle.get_person_from_handle(_handle)
        if person:
            person.remove_note(note_handle)
            db_handle.commit_person(person, trans)

    for _handle in family_list:
        family = db_handle.get_family_from_handle(_handle)
        if family:
            family.remove_note(note_handle)
            db_handle.commit_family(family, trans)

    for _handle in event_list:
        event = db_handle.get_event_from_handle(_handle)
        if event:
            event.remove_note(note_handle)
            db_handle.commit_event(event, trans)

    for _handle in place_list:
        place = db_handle.get_place_from_handle(_handle)
        if place:
            place.remove_note(note_handle)
            db_handle.commit_place(place, trans)

    for _handle in source_list:
        source = db_handle.get_source_from_handle(_handle)
        if source:
            source.remove_note(note_handle)
            db_handle.commit_source(source, trans)

    for _handle in citation_list:
        citation = db_handle.get_citation_from_handle(_handle)
        if citation:
            citation.remove_note(note_handle)
            db_handle.commit_citation(citation, trans)

    for _handle in media_list:
        media = db_handle.get_media_from_handle(_handle)
        if media:
            media.remove_note(note_handle)
            db_handle.commit_media(media, trans)

    for _handle in repo_list:
        repo = db_handle.get_repository_from_handle(_handle)
        if repo:
            repo.remove_note(note_handle)
            db_handle.commit_repository(repo, trans)

    db_handle.remove_note(note_handle, trans)


def delete_place(db_handle: DbWriteBase, handle: str, trans: DbTxn) -> None:
    """Delete a place and its references."""
    person_list = [
        item[1] for item in db_handle.find_backlink_handles(handle, ["Person"])
    ]

    family_list = [
        item[1] for item in db_handle.find_backlink_handles(handle, ["Family"])
    ]

    event_list = [
        item[1] for item in db_handle.find_backlink_handles(handle, ["Event"])
    ]

    for _handle in person_list:
        person = db_handle.get_person_from_handle(_handle)
        person.remove_handle_references("Place", handle)
        db_handle.commit_person(person, trans)

    for _handle in family_list:
        family = db_handle.get_family_from_handle(_handle)
        family.remove_handle_references("Place", handle)
        db_handle.commit_family(family, trans)

    for _handle in event_list:
        event = db_handle.get_event_from_handle(_handle)
        event.remove_handle_references("Place", handle)
        db_handle.commit_event(event, trans)

    db_handle.remove_place(handle, trans)


def delete_repository(db_handle: DbWriteBase, handle: str, trans: DbTxn) -> None:
    """Delete a repository and its references."""
    souce_list = [
        item[1] for item in db_handle.find_backlink_handles(handle, ["Source"])
    ]

    repos_handle_list = [handle]

    for _handle in souce_list:
        source = db_handle.get_source_from_handle(_handle)
        source.remove_repo_references(repos_handle_list)
        db_handle.commit_source(source, trans)

    db_handle.remove_repository(handle, trans)


def delete_source(db_handle: DbWriteBase, handle: str, trans: DbTxn) -> None:
    """Delete a source and its references."""
    # we can have:
    # object(CitationBase) -> Citation(source_handle) -> Source
    # We first have to remove the CitationBase references to the
    # Citation. Then we remove the Citations. (We don't need to
    # remove the source_handle references to the Source, because we are
    # removing the whole Citation). Then we can remove the Source
    (citation_list, citation_referents_list) = get_source_and_citation_referents(
        handle, db_handle
    )

    # citation_list is a tuple of lists. Only the first, for Citations,
    # exists.
    citation_list = citation_list[0]

    # (1) delete the references to the citation
    for citation_handle, refs in citation_referents_list:
        (
            person_list,
            family_list,
            event_list,
            place_list,
            source_list,
            media_list,
            repo_list,
        ) = refs

        ctn_handle_list = [citation_handle]

        for _handle in person_list:
            person = db_handle.get_person_from_handle(_handle)
            person.remove_citation_references(ctn_handle_list)
            db_handle.commit_person(person, trans)

        for _handle in family_list:
            family = db_handle.get_family_from_handle(_handle)
            family.remove_citation_references(ctn_handle_list)
            db_handle.commit_family(family, trans)

        for _handle in event_list:
            event = db_handle.get_event_from_handle(_handle)
            event.remove_citation_references(ctn_handle_list)
            db_handle.commit_event(event, trans)

        for _handle in place_list:
            place = db_handle.get_place_from_handle(_handle)
            place.remove_citation_references(ctn_handle_list)
            db_handle.commit_place(place, trans)

        for _handle in source_list:
            source = db_handle.get_source_from_handle(_handle)
            source.remove_citation_references(ctn_handle_list)
            db_handle.commit_source(source, trans)

        for _handle in media_list:
            media = db_handle.get_media_from_handle(_handle)
            media.remove_citation_references(ctn_handle_list)
            db_handle.commit_media(media, trans)

        for _handle in repo_list:
            repo = db_handle.get_repository_from_handle(_handle)
            repo.remove_citation_references(ctn_handle_list)
            db_handle.commit_repository(repo, trans)

    for citation_handle in citation_list:
        db_handle.remove_citation(citation_handle, trans)

    db_handle.remove_source(handle, trans)


def delete_tag(db_handle: DbWriteBase, handle: str, trans: DbTxn) -> None:
    """Delete a tag."""
    fnc = {
        "Person": (db_handle.get_person_from_handle, db_handle.commit_person),
        "Family": (db_handle.get_family_from_handle, db_handle.commit_family),
        "Event": (db_handle.get_event_from_handle, db_handle.commit_event),
        "Place": (db_handle.get_place_from_handle, db_handle.commit_place),
        "Source": (db_handle.get_source_from_handle, db_handle.commit_source),
        "Citation": (db_handle.get_citation_from_handle, db_handle.commit_citation),
        "Repository": (
            db_handle.get_repository_from_handle,
            db_handle.commit_repository,
        ),
        "Media": (db_handle.get_media_from_handle, db_handle.commit_media),
        "Note": (db_handle.get_note_from_handle, db_handle.commit_note),
    }
    links = db_handle.find_backlink_handles(handle)

    for classname, _handle in links:
        obj = fnc[classname][0](_handle)  # get from handle
        obj.remove_tag(handle)
        fnc[classname][1](obj, trans)  # commit
    db_handle.remove_tag(handle, trans)


delete_methods = {
    "person": delete_person,
    "family": delete_family,
    "event": delete_event,
    "place": delete_place,
    "media": delete_media,
    "note": delete_note,
    "repository": delete_repository,
    "source": delete_source,
    "citation": delete_citation,
    "tag": delete_tag,
}


def delete_object(
    db_handle: DbWriteBase, handle: str, gramps_class_name: str
) -> List[Dict[str, Any]]:
    """Delete the object and its references."""
    key = gramps_class_name.lower()
    try:
        method = delete_methods[key]
    except KeyError:
        raise NotImplementedError(gramps_class_name)
    with DbTxn(f"Delete {gramps_class_name}", db_handle) as trans:
        method(db_handle, handle, trans=trans)
        trans_dict = transaction_to_json(trans)
    return trans_dict


def delete_all_objects(
    db_handle: DbWriteBase,
    namespaces: Optional[List[str]] = None,
    progress_cb: Optional[Callable] = None,
) -> None:
    """Delete all objects, optionally restricting to one or more types (namespaces)."""
    if progress_cb:
        total = get_total_number_of_objects(db_handle)
    if namespaces is not None:
        unknown_namespaces = set(namespaces) - set(GRAMPS_OBJECT_PLURAL.values())
        if unknown_namespaces:
            raise ValueError(f"Unknown namespace {unknown_namespaces}")
    i = 0
    for class_name, namespace in GRAMPS_OBJECT_PLURAL.items():
        if namespaces is None or namespace in namespaces:
            with DbTxn(f"Delete {namespaces or 'all objects'}", db_handle) as trans:
                iter_handles = db_handle.method("iter_%s_handles", class_name)
                del_method = delete_methods[class_name.lower()]
                for handle in iter_handles():
                    if progress_cb:
                        progress_cb(current=i, total=total)
                    i += 1
                    del_method(db_handle=db_handle, handle=handle, trans=trans)
