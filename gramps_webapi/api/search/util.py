#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2020-2024      David Straub
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

"""Full-text search utility functions."""

from gramps.gen.db.base import DbReadBase


def get_total_number_of_objects(db_handle: DbReadBase):
    """Get the total number of searchable objects in the database."""
    return (
        db_handle.get_number_of_people()
        + db_handle.get_number_of_families()
        + db_handle.get_number_of_sources()
        + db_handle.get_number_of_citations()
        + db_handle.get_number_of_events()
        + db_handle.get_number_of_media()
        + db_handle.get_number_of_places()
        + db_handle.get_number_of_repositories()
        + db_handle.get_number_of_notes()
        + db_handle.get_number_of_tags()
    )
