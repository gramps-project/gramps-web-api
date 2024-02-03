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

from gramps.gen.db import DbTxn, DbWriteBase
from gramps.gen.dbstate import DbState
from gramps.plugins.tool.check import CheckIntegrity


def check_database(db_handle: DbWriteBase):
    with DbTxn("Check Integrity", db_handle, batch=True) as trans:
        db_handle.disable_signals()
        dbstate = DbState()
        dbstate.change_database(db_handle)
        checker = CheckIntegrity(dbstate, None, trans)

        # start with empty objects, broken links can be corrected below
        # then. This is done before fixing encoding and missing photos,
        # since otherwise we will be trying to fix empty records which are
        # then going to be deleted.
        checker.cleanup_empty_objects()
        checker.fix_encoding()
        checker.fix_alt_place_names()
        checker.fix_ctrlchars_in_notes()
        # checker.cleanup_missing_photos(cli=1)  # should not be done on Web API
        checker.cleanup_deleted_name_formats()

        prev_total = -1
        total = 0

        while prev_total != total:
            prev_total = total

            checker.check_for_broken_family_links()
            checker.check_parent_relationships()
            checker.cleanup_empty_families(1)
            checker.cleanup_duplicate_spouses()

            total = checker.family_errors()

        checker.fix_duplicated_grampsid()
        checker.check_events()
        checker.check_person_references()
        checker.check_family_references()
        checker.check_place_references()
        checker.check_source_references()
        checker.check_citation_references()
        checker.check_media_references()
        checker.check_repo_references()
        checker.check_note_references()
        checker.check_tag_references()
        # checker.check_checksum()  # should not be done on Web API
        checker.check_media_sourceref()
        # checker.check_note_links()  # requires Gramps 5.2
        checker.check_backlinks()

    # rebuilding reference maps needs to be done outside of a transaction
    # to avoid nesting transactions.
    if checker.bad_backlinks:
        checker.progress.set_pass("Rebuilding reference maps...", 6)
        db_handle.reindex_reference_map(checker.callback)

    db_handle.enable_signals()
    db_handle.request_rebuild()

    errs = checker.build_report()
    text = checker.text.getvalue()
    return {"num_errors": errs, "message": text}
