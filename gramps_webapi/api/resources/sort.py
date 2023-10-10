#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2007  Donald N. Allingham
# Copyright (C) 2020       Christopher Horn
# Copyright (C) 2023       David Straub
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

"""Sorting support."""

from typing import List

from flask import abort
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.display.name import NameDisplay
from gramps.gen.display.place import PlaceDisplay
from gramps.gen.lib import Date
from gramps.gen.lib.primaryobj import BasicPrimaryObject as GrampsObject
from gramps.gen.soundex import soundex
from gramps.gen.utils.db import get_birth_or_fallback, get_death_or_fallback


class Sort:
    """Class for extracting sort keys."""

    def __init__(self, database, locale=glocale):
        """Initialize sort class."""
        self.database = database
        self.locale = locale
        self.name_display = NameDisplay(xlocale=self.locale)
        self.place_display = PlaceDisplay()

    # Generic object key methods

    def by_id_key(self, obj: GrampsObject):
        """Compare by Gramps Id."""
        return self.locale.sort_key(obj.gramps_id)

    def by_change_key(self, obj: GrampsObject):
        """Compare by last change."""
        return obj.change

    def by_private_key(self, obj: GrampsObject):
        """Compare based on private attribute."""
        return int(obj.private)

    def by_date_key(self, obj: GrampsObject):
        """Compare by date."""
        return obj.get_date_object().get_sort_value()

    def by_type_key(self, obj: GrampsObject):
        """Compare by type."""
        return self.locale.sort_key(
            self.locale.translation.sgettext(str(obj.get_type()))
        )

    # Specific object key methods

    def by_person_surname_key(self, obj: GrampsObject):
        """Compare by surname, if equal uses given name and suffix."""
        name = obj.get_primary_name()
        fsn = name.get_surname()
        ffn = name.get_first_name()
        fsu = name.get_suffix()
        return self.locale.sort_key(fsn + ffn + fsu)

    def by_person_sorted_name_key(self, obj: GrampsObject):
        """Compare by displayed names."""
        return self.locale.sort_key(self.name_display.sorted(obj))

    def by_person_soundex_key(self, obj: GrampsObject):
        """Compare by soundex."""
        return soundex(obj.get_primary_name().get_surname())

    def by_person_birthdate_key(self, obj: GrampsObject):
        """Compare by birth date, if equal sorts by name."""
        birth = get_birth_or_fallback(self.database, obj)
        if birth:
            date = birth.get_date_object()
        else:
            date = Date()
        return "%08d" % date.get_sort_value() + str(self.by_person_surname_key(obj))

    def by_person_deathdate_key(self, obj: GrampsObject):
        """Compare by death date, if equal sorts by name."""
        death = get_death_or_fallback(self.database, obj)
        if death:
            date = death.get_date_object()
        else:
            date = Date()
        return "%08d" % date.get_sort_value() + str(self.by_person_surname_key(obj))

    def by_person_gender_key(self, obj: GrampsObject):
        """Compare by gender."""
        return obj.gender

    def by_family_surname_key(self, obj: GrampsObject):
        """Compare by family surname, if equal uses given and suffix."""
        if obj.father_handle is not None:
            person = self.database.get_person_from_handle(obj.father_handle)
        elif obj.mother_handle is not None:
            person = self.database.get_person_from_handle(obj.mother_handle)
        name = person.get_primary_name()
        fsn = name.get_surname()
        ffn = name.get_first_name()
        fsu = name.get_suffix()
        return self.locale.sort_key(fsn + ffn + fsu)

    def by_family_soundex_key(self, obj: GrampsObject):
        """Compare by family soundex."""
        if obj.father_handle is not None:
            person = self.database.get_person_from_handle(obj.father_handle)
        elif obj.mother_handle is not None:
            person = self.database.get_person_from_handle(obj.mother_handle)
        return soundex(person.get_primary_name().get_surname())

    def by_family_type_key(self, obj: GrampsObject):
        """Compare by relationship type."""
        return self.locale.sort_key(self.locale.translation.sgettext(str(obj.type)))

    def by_event_place_key(self, obj: GrampsObject):
        """Compare by event place."""
        return self.locale.sort_key(
            self.place_display.display_event(self.database, obj)
        )

    def by_event_description_key(self, obj: GrampsObject):
        """Compare by event description."""
        return self.locale.sort_key(obj.get_description())

    def by_place_title_key(self, obj: GrampsObject):
        """Compare by place title."""
        return self.locale.sort_key(self.place_display.display(self.database, obj))

    def by_place_latitude_key(self, obj: GrampsObject):
        """Compare by place latitude."""
        return obj.lat

    def by_place_longitude_key(self, obj: GrampsObject):
        """Compare by place longitude."""
        return obj.long

    def by_citation_confidence_key(self, obj: GrampsObject):
        """Compare by citation confidence."""
        return obj.confidence

    def by_source_title_key(self, obj: GrampsObject):
        """Compare by source title."""
        return self.locale.sort_key(obj.title)

    def by_source_author_key(self, obj: GrampsObject):
        """Compare by source title."""
        return self.locale.sort_key(obj.author)

    def by_source_pubinfo_key(self, obj: GrampsObject):
        """Compare by source publication info."""
        return self.locale.sort_key(obj.pubinfo)

    def by_source_abbrev_key(self, obj: GrampsObject):
        """Compare by source abbreviation."""
        return obj.abbrev

    def by_repository_name_key(self, obj: GrampsObject):
        """Compare by repository name."""
        return self.locale.sort_key(obj.name)

    def by_media_title_key(self, obj: GrampsObject):
        """Compare by media title."""
        return self.locale.sort_key(obj.desc)

    def by_media_path_key(self, obj: GrampsObject):
        """Compare by media path."""
        return obj.path

    def by_media_mimetype_key(self, obj: GrampsObject):
        """Compare by media mime type."""
        return obj.mime

    def by_note_text_key(self, obj: GrampsObject):
        """Compare by note text."""
        return self.locale.sort_key(obj.text.string)

    def by_tag_name_key(self, obj: GrampsObject):
        """Compare by tag name."""
        return self.locale.sort_key(obj.name)

    def by_tag_color_key(self, obj: GrampsObject):
        """Compare by tag color."""
        return obj.color

    def by_tag_priority_key(self, obj: GrampsObject):
        """Compare by tag priority."""
        return obj.priority


def sort_objects(
    db_handle, gramps_class_name: str, objects: List[GrampsObject], args, locale=glocale
) -> List[GrampsObject]:
    """Sort a given set of object handles."""
    sort = Sort(db_handle, locale=locale)
    lookup = {
        "gramps_id": sort.by_id_key,
        "change": sort.by_change_key,
        "private": sort.by_private_key,
    }
    if gramps_class_name == "Person":
        lookup.update(
            {
                "surname": sort.by_person_surname_key,
                "name": sort.by_person_sorted_name_key,
                "soundex": sort.by_person_soundex_key,
                "birth": sort.by_person_birthdate_key,
                "death": sort.by_person_deathdate_key,
                "gender": sort.by_person_gender_key,
            }
        )
    elif gramps_class_name == "Family":
        lookup.update(
            {
                "surname": sort.by_family_surname_key,
                "type": sort.by_family_type_key,
                "soundex": sort.by_family_soundex_key,
            }
        )
    elif gramps_class_name == "Event":
        lookup.update(
            {
                "date": sort.by_date_key,
                "type": sort.by_type_key,
                "description": sort.by_event_description_key,
                "place": sort.by_event_place_key,
            }
        )
    elif gramps_class_name == "Place":
        lookup.update(
            {
                "title": sort.by_place_title_key,
                "type": sort.by_type_key,
                "latitude": sort.by_place_latitude_key,
                "longitude": sort.by_place_longitude_key,
            }
        )
    elif gramps_class_name == "Citation":
        lookup.update(
            {"date": sort.by_date_key, "confidence": sort.by_citation_confidence_key}
        )
    elif gramps_class_name == "Source":
        lookup.update(
            {
                "title": sort.by_source_title_key,
                "author": sort.by_source_author_key,
                "pubinfo": sort.by_source_pubinfo_key,
                "abbrev": sort.by_source_abbrev_key,
            }
        )
    elif gramps_class_name == "Repository":
        lookup.update({"name": sort.by_repository_name_key, "type": sort.by_type_key})
    elif gramps_class_name == "Media":
        lookup.update(
            {
                "title": sort.by_media_title_key,
                "path": sort.by_media_path_key,
                "mime": sort.by_media_mimetype_key,
                "date": sort.by_date_key,
            }
        )
    elif gramps_class_name == "Note":
        lookup.update({"type": sort.by_type_key, "text": sort.by_note_text_key})
    elif gramps_class_name == "Tag":
        lookup = {
            "change": sort.by_change_key,
            "name": sort.by_tag_name_key,
            "color": sort.by_tag_color_key,
            "priority": sort.by_tag_priority_key,
        }

    for sort_key in args:
        sort_key = sort_key.strip()
        reverse = False
        if sort_key[:1] == "-":
            reverse = True
            sort_key = sort_key[1:]
        if sort_key not in lookup:
            abort(422)
        objects.sort(key=lookup[sort_key], reverse=reverse)
    return objects
