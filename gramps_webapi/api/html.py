"""HTML backend for styled text."""

import bleach

from gramps.gen.lib import Note, NoteType, StyledText
from gramps.plugins.lib.libhtml import Html
from gramps.plugins.lib.libhtmlbackend import HtmlBackend, process_spaces


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

ALLOWED_STYLES = [
    "color",
    "background-color",
    "font-family",
    "font-weight",
    "font-size",
    "font-style",
    "text-decoration",
]


def sanitize(html: str):
    """Sanitize an HTML string by keeping only allowed tags/attributes."""
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        styles=ALLOWED_STYLES,
        strip=True,
    )


def get_note_html(note: Note):
    """Return a note text as sanitized HTML."""
    html_note_text = styledtext_to_html(
        styledtext=note.get_styledtext(),
        space_format=note.get_format(),
        contains_html=(note.get_type() == NoteType.HTML_CODE),
    )
    return sanitize(html_note_text)


def styledtext_to_html(
    styledtext: StyledText, space_format: int, contains_html: bool = False
):
    """Return the note in HTML format.

    Adapted from DynamicWeb.
    """
    backend = HtmlBackend()

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
