#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2007  Donald N. Allingham
# Copyright (C) 2008       Brian G. Matherly
# Copyright (C) 2010       Jakim Friant
# Copyright (C) 2011       Tim G L Lyons
# Copyright (C) 2012       Michiel D. Nauta
# Copyright (C) 2025       David Straub
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
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Check and repair a Gramps database."""

from collections import defaultdict
from typing import Callable, Optional

from gramps.gen.db import DbTxn, DbWriteBase
from gramps.gen.dbstate import DbState
from gramps.plugins.tool.check import CheckIntegrity

# db.<attr> caches of custom type values (e.g. db.event_names); only ever
# grow as records commit, so they need rebuilding from live data here.
CUSTOM_TYPE_CACHE_ATTRS = (
    "event_attributes",
    "family_attributes",
    "media_attributes",
    "individual_attributes",
    "event_role_names",
    "event_names",
    "family_rel_types",
    "child_ref_types",
    "origin_types",
    "name_types",
    "note_types",
    "place_types",
    "repository_types",
    "source_attributes",
    "source_media_types",
    "url_types",
)


def rebuild_custom_type_caches(db_handle: DbWriteBase) -> list[tuple[str, str]]:
    """Recompute the database's custom-type caches from data in use now.

    Returns the list of (attribute, value) pairs removed as stale.
    """
    fresh = defaultdict(set)

    def add_custom(attr, type_obj):
        if type_obj.is_custom():
            value = str(type_obj)
            if value:
                fresh[attr].add(value)

    def add_media_attributes(media_list):
        for mref in media_list:
            for attr in mref.attribute_list:
                add_custom("media_attributes", attr.type)

    for person in db_handle.iter_people():
        for attr in person.attribute_list:
            add_custom("individual_attributes", attr.type)
        for eref in person.event_ref_list:
            add_custom("event_role_names", eref.role)
        for name in [person.primary_name] + person.alternate_names:
            add_custom("name_types", name.type)
            for surname in name.get_surname_list():
                add_custom("origin_types", surname.origintype)
        for url in person.urls:
            add_custom("url_types", url.type)
        add_media_attributes(person.media_list)

    for family in db_handle.iter_families():
        for attr in family.attribute_list:
            add_custom("family_attributes", attr.type)
        for ref in family.child_ref_list:
            add_custom("child_ref_types", ref.frel)
            add_custom("child_ref_types", ref.mrel)
        for eref in family.event_ref_list:
            add_custom("event_role_names", eref.role)
        add_custom("family_rel_types", family.type)
        add_media_attributes(family.media_list)

    for event in db_handle.iter_events():
        for attr in event.attribute_list:
            add_custom("event_attributes", attr.type)
        add_custom("event_names", event.type)
        add_media_attributes(event.media_list)

    for place in db_handle.iter_places():
        add_custom("place_types", place.get_type())
        for url in place.urls:
            add_custom("url_types", url.type)
        add_media_attributes(place.media_list)

    for source in db_handle.iter_sources():
        for ref in source.reporef_list:
            add_custom("source_media_types", ref.media_type)
        for attr in source.attribute_list:
            add_custom("source_attributes", attr.type)
        add_media_attributes(source.media_list)

    for citation in db_handle.iter_citations():
        for attr in citation.attribute_list:
            add_custom("source_attributes", attr.type)
        add_media_attributes(citation.media_list)

    for repository in db_handle.iter_repositories():
        add_custom("repository_types", repository.type)
        for url in repository.urls:
            add_custom("url_types", url.type)

    for note in db_handle.iter_notes():
        add_custom("note_types", note.type)

    for media in db_handle.iter_media():
        for attr in media.attribute_list:
            add_custom("media_attributes", attr.type)

    removed: list[tuple[str, str]] = []
    for attr_name in CUSTOM_TYPE_CACHE_ATTRS:
        cache = getattr(db_handle, attr_name, None)
        if cache is None:
            continue
        stale = set(cache) - fresh[attr_name]
        removed.extend((attr_name, value) for value in sorted(stale))
        cache.clear()
        cache.update(fresh[attr_name])

    return removed


def check_database(db_handle: DbWriteBase, progress_cb: Optional[Callable] = None):
    i = 0

    def progress(i):
        total = 21
        if progress_cb:
            progress_cb(current=i, total=total)
        i += 1
        return i

    with DbTxn("Check Integrity", db_handle, batch=True) as trans:
        db_handle.disable_signals()
        dbstate = DbState()
        dbstate.change_database(db_handle)
        checker = CheckIntegrity(dbstate, None, trans)

        # start with empty objects, broken links can be corrected below
        # then. This is done before fixing encoding and missing photos,
        # since otherwise we will be trying to fix empty records which are
        # then going to be deleted.

        i = progress(i)
        checker.cleanup_empty_objects()

        i = progress(i)
        checker.fix_encoding()

        i = progress(i)
        checker.fix_alt_place_names()

        i = progress(i)
        checker.fix_ctrlchars_in_notes()
        # checker.cleanup_missing_photos(cli=1)  # should not be done on Web API

        i = progress(i)
        checker.cleanup_deleted_name_formats()

        prev_total = -1
        total = 0

        i = progress(i)
        while prev_total != total:
            prev_total = total

            checker.check_for_broken_family_links()
            checker.check_parent_relationships()
            checker.cleanup_empty_families(1)
            checker.cleanup_duplicate_spouses()

            total = checker.family_errors()

        i = progress(i)
        checker.fix_duplicated_grampsid()

        i = progress(i)
        checker.check_events()

        i = progress(i)
        checker.check_person_references()

        i = progress(i)
        checker.check_family_references()

        i = progress(i)
        checker.check_place_references()

        i = progress(i)
        checker.check_source_references()

        i = progress(i)
        checker.check_citation_references()

        i = progress(i)
        checker.check_media_references()

        i = progress(i)
        checker.check_repo_references()

        i = progress(i)
        checker.check_note_references()

        i = progress(i)
        checker.check_tag_references()
        # checker.check_checksum()  # should not be done on Web API

        i = progress(i)
        checker.check_media_sourceref()
        # checker.check_note_links()  # requires Gramps 5.2

        i = progress(i)
        checker.check_backlinks()

        i = progress(i)
        removed_custom_types = rebuild_custom_type_caches(db_handle)

    # rebuilding reference maps needs to be done outside of a transaction
    # to avoid nesting transactions.
    i = progress(i)
    if checker.bad_backlinks:
        checker.progress.set_pass("Rebuilding reference maps...", 6)
        db_handle.reindex_reference_map(checker.callback)

    db_handle.enable_signals()
    db_handle.request_rebuild()

    errs = checker.build_report() + len(removed_custom_types)
    text = checker.text.getvalue()
    if removed_custom_types:
        text += (
            f"{len(removed_custom_types)} unused custom type value(s) were "
            "removed from the type selector lists\n"
        )
    return {"num_errors": errs, "message": text}
