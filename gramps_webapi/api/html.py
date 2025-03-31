#
# Gramps Web API - A RESTful API for the Gramps genealogy program
#
# Copyright (C) 2009      Gerald Britton <gerald.britton@gmail.com>
# Copyright (C) 2020      David Straub
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

"""HTML backend for styled text."""

from typing import Callable, Optional

import bleach  # type: ignore
from bleach.css_sanitizer import CSSSanitizer  # type: ignore
from gramps.gen.errors import HandleError
from gramps.gen.lib import Note, NoteType, StyledText
from gramps.plugins.lib.libhtml import Html
from gramps.plugins.lib.libhtmlbackend import HtmlBackend, process_spaces

from .util import get_db_handle

ALLOWED_TAGS = [
    "a",
    "abbr",
    "acronym",
    "b",
    "blockquote",
    "code",
    "em",
    "i",
    "li",
    "ol",
    "strong",
    "ul",
    "span",
    "p",
    "br",
    "div",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "style"],
    "abbr": ["title", "style"],
    "acronym": ["title", "style"],
    "p": ["style"],
    "div": ["style"],
    "span": ["style"],
}

ALLOWED_CSS_PROPERTIES = [
    "color",
    "background-color",
    "font-family",
    "font-weight",
    "font-size",
    "font-style",
    "text-decoration",
]


CSS_SANITIZER = CSSSanitizer(allowed_css_properties=ALLOWED_CSS_PROPERTIES)


def sanitize(html: str):
    """Sanitize an HTML string by keeping only allowed tags/attributes."""
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        css_sanitizer=CSS_SANITIZER,
        strip=True,
    )


def get_note_html(note: Note, link_format: Optional[str] = None) -> str:
    """Return a note text as sanitized HTML."""
    html_note_text = styledtext_to_html(
        styledtext=note.get_styledtext(),
        space_format=note.get_format(),
        contains_html=(note.get_type() == NoteType.HTML_CODE),
        link_format=link_format,
    )
    return sanitize(html_note_text)


def build_link_factory(link_format: Optional[str] = None) -> Optional[Callable]:
    """Return a build link function."""
    if link_format is None:
        return None

    def build_link(prop: str, handle: str, obj_class: str) -> str:
        """Build a link to an item."""
        db_handle = get_db_handle()
        if prop == "gramps_id":
            gramps_id = handle
            func = db_handle.method("get_%s_from_gramps_id", obj_class)
            obj = func(gramps_id)
            if not obj:
                return ""
            ref = obj.handle
        elif prop == "handle":
            ref = handle
            func = db_handle.method("get_%s_from_handle", obj_class)
            try:
                obj = func(ref)
            except HandleError:
                return ""
            if not obj:
                return ""
            gramps_id = obj.gramps_id
        else:
            raise ValueError(f"Unexpected property: {prop}")
        return link_format.format(
            obj_class=obj_class.lower(), gramps_id=gramps_id, handle=ref
        )

    return build_link


def styledtext_to_html(
    styledtext: StyledText,
    space_format: int,
    contains_html: bool = False,
    link_format: Optional[str] = None,
):
    """Return the note in HTML format.

    Adapted from DynamicWeb.
    """
    backend = HtmlBackend()
    if link_format is not None:
        backend.build_link = build_link_factory(link_format)

    text = str(styledtext)

    if not text:
        return ""

    s_tags = styledtext.get_tags()
    html_list = Html("div", class_="grampsstylednote")
    if contains_html:
        markuptext = backend.add_markup_from_styled(
            text, s_tags, split="\n", escape=False
        )
        html_list += markuptext
    else:
        markuptext = backend.add_markup_from_styled(text, s_tags, split="\n")
        linelist = []
        linenb = 1
        sigcount = 0
        for line in markuptext.split("\n"):
            [line, sigcount] = process_spaces(line, format=space_format)
            if sigcount == 0:
                # The rendering of an empty paragraph '<p></p>'
                # is undefined so we use a non-breaking space
                if linenb == 1:
                    linelist.append("&nbsp;")
                html_list.extend(Html("p") + linelist)
                linelist = []
                linenb = 1
            else:
                if linenb > 1:
                    linelist[-1] += "<br />"
                linelist.append(line)
                linenb += 1
        if linenb > 1:
            html_list.extend(Html("p") + linelist)
        # if the last line was blank, then as well as outputting the previous para,
        # which we have just done,
        # we also output a new blank para
        if sigcount == 0:
            linelist = ["&nbsp;"]
            html_list.extend(Html("p") + linelist)
    return "\n".join(html_list)
