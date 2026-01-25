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
from gramps.plugins.tool.check import CheckIntegrity


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
    return {"num_errors": errs, "message": text}
