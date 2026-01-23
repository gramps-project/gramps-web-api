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

from typing import Callable, Optional

from gramps.gen.db import DbTxn, DbWriteBase
from gramps.gen.dbstate import DbState
from gramps.gen.lib import (
    Citation,
    Event,
    Family,
    Media,
    Note,
    Person,
    Place,
    Repository,
    Source,
    Tag,
)
from gramps.gen.lib.serialize import data_to_object, object_to_dict
from gramps.plugins.tool.check import CheckIntegrity

from .util import get_logger, strip_whitespace_recursive


def check_database(db_handle: DbWriteBase, progress_cb: Optional[Callable] = None):
    i = 0

    def progress(i):
        total = 20
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

    # rebuilding reference maps needs to be done outside of a transaction
    # to avoid nesting transactions.
    i = progress(i)
    if checker.bad_backlinks:
        checker.progress.set_pass("Rebuilding reference maps...", 6)
        db_handle.reindex_reference_map(checker.callback)

    db_handle.enable_signals()
    db_handle.request_rebuild()

    errs = checker.build_report()
    text = checker.text.getvalue()

    # Strip trailing whitespace from all objects
    i = progress(i)
    whitespace_fixes = strip_trailing_whitespace(db_handle, progress_cb)
    if whitespace_fixes > 0:
        text += f"\n\nStripped surrounding whitespace from {whitespace_fixes} objects."

    return {"num_errors": errs, "message": text}


def strip_trailing_whitespace(
    db_handle: DbWriteBase, progress_cb: Optional[Callable] = None
) -> int:
    """Strip leading and trailing whitespace from all string properties in database objects.

    This ensures database content matches the normalized form that Gramps uses for
    XML export, preventing spurious differences during sync operations.

    Args:
        db_handle: The database to process
        progress_cb: Optional progress callback

    Returns:
        Number of objects that were modified
    """
    fixes = 0
    total_objects = (
        db_handle.get_number_of_people()
        + db_handle.get_number_of_families()
        + db_handle.get_number_of_events()
        + db_handle.get_number_of_places()
        + db_handle.get_number_of_sources()
        + db_handle.get_number_of_citations()
        + db_handle.get_number_of_repositories()
        + db_handle.get_number_of_media()
        + db_handle.get_number_of_notes()
        + db_handle.get_number_of_tags()
    )

    if progress_cb:
        progress_cb(current=0, total=total_objects)

    processed = 0

    # Process each object type
    object_types = [
        (
            "Person",
            Person,
            db_handle.get_person_handles,
            db_handle.get_person_from_handle,
            db_handle.commit_person,
        ),
        (
            "Family",
            Family,
            db_handle.get_family_handles,
            db_handle.get_family_from_handle,
            db_handle.commit_family,
        ),
        (
            "Event",
            Event,
            db_handle.get_event_handles,
            db_handle.get_event_from_handle,
            db_handle.commit_event,
        ),
        (
            "Place",
            Place,
            db_handle.get_place_handles,
            db_handle.get_place_from_handle,
            db_handle.commit_place,
        ),
        (
            "Source",
            Source,
            db_handle.get_source_handles,
            db_handle.get_source_from_handle,
            db_handle.commit_source,
        ),
        (
            "Citation",
            Citation,
            db_handle.get_citation_handles,
            db_handle.get_citation_from_handle,
            db_handle.commit_citation,
        ),
        (
            "Repository",
            Repository,
            db_handle.get_repository_handles,
            db_handle.get_repository_from_handle,
            db_handle.commit_repository,
        ),
        (
            "Media",
            Media,
            db_handle.get_media_handles,
            db_handle.get_media_from_handle,
            db_handle.commit_media,
        ),
        (
            "Note",
            Note,
            db_handle.get_note_handles,
            db_handle.get_note_from_handle,
            db_handle.commit_note,
        ),
        (
            "Tag",
            Tag,
            db_handle.get_tag_handles,
            db_handle.get_tag_from_handle,
            db_handle.commit_tag,
        ),
    ]

    with DbTxn("Strip surrounding whitespace", db_handle, batch=True) as trans:
        for obj_type_name, obj_class, get_handles, get_obj, commit_obj in object_types:
            for handle in get_handles():
                try:
                    obj = get_obj(handle)
                    # Serialize to dict, strip whitespace, deserialize back
                    obj_dict = object_to_dict(obj)
                    obj_dict_stripped = strip_whitespace_recursive(obj_dict)

                    # Check if anything changed
                    if obj_dict != obj_dict_stripped:
                        # Deserialize and commit the modified object
                        obj_modified = data_to_object(obj_dict_stripped)
                        commit_obj(obj_modified, trans)
                        fixes += 1

                    processed += 1
                    if progress_cb and processed % 100 == 0:
                        progress_cb(current=processed, total=total_objects)

                except Exception as e:
                    # Log but don't fail - continue processing other objects
                    logger = get_logger()
                    logger.error(f"Error processing {obj_type_name} {handle}: {e}")
                    continue

    if progress_cb:
        progress_cb(current=total_objects, total=total_objects)

    return fixes
